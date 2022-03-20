from threading import Thread
from binance.client import Client
from binance import ThreadedWebsocketManager
import configparser
import sqlite3
import logging
from websocket_server import WebsocketServer
import json
from multiprocessing import Queue
import webbrowser
from pathlib import Path


config = configparser.ConfigParser()
config.read_file(open("Config.cfg"))
key = config.get('KEY', 'API_KEY')
secret = config.get('KEY', 'SECRET_KEY')
client = Client(api_key=key, api_secret=secret)

conn = sqlite3.connect("Data.sqlite3")
cur = conn.cursor()

queue = Queue()

currency_list = {}  # Список валютных пар по которым идёт торговля с открытыми по ним ордерами и настройками


def cancel_orders():
    """
    Метод для тестирования, чтобы отчистить аккаунт от лотов
    """
    orders = client.get_open_orders(symbol='DOGERUB')
    print("Ордеров:", len(orders))
    print(client.get_asset_balance('RUB'))
    print(client.get_asset_balance('DOGE'))
    if len(orders) > 0:
        for order in orders:
            client.cancel_order(symbol=order['symbol'], orderId=order['orderId'])
            print("Удалён ордер:", order['orderId'])
        print(client.get_asset_balance('RUB'))
        print(client.get_asset_balance('DOGE'))


def create_order(symbol, side, price, volume, echo=False):
    """
    Создаёт лот на Бинансе
    """
    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type='LIMIT',
            timeInForce='GTC',
            quantity=volume,
            price=price)
        if echo is True:
            print('Создан ордер:', symbol, side, price)
        return order
    except Exception as e:
        print(side, price)
        print("Ошибка сервера - {}".format(e))
        return False


def init_trade(conf):
    """
    Инициализируем торговлю по заданной паре
    Создаём пул ордеров на покупку и продажу
    """
    if conf['symbol'] in currency_list:
        print(f"Валютная пара {conf['symbol']} уже присутствует")
        return

    info = client.get_symbol_info(symbol=conf['symbol'])
    # Для удобства и надёжности (вдруго сменится последовательность фильтров) заполним словарь, где ключ - имя фильтра
    filters = {}
    for fil in info['filters']:
        filters[fil['filterType']] = fil

    if conf['step'] < float(filters['PRICE_FILTER']['tickSize']):
        print("EXCEPTION: Недопустимый шаг цены")
        return False
    if conf['volume'] > float(filters['LOT_SIZE']['maxQty']) or conf['volume'] < float(filters['LOT_SIZE']['minQty']):
        print("EXCEPTION: Недопустимый обэём лота")
        return False

    # avg_price = client.get_avg_price(symbol=conf['symbol'])
    avg_price = client.get_symbol_ticker(symbol=conf['symbol'])
    avg_price = float(avg_price['price'])
    # Округлим цену чтобы соблюсти точность API
    tick_size = float(filters['PRICE_FILTER']['tickSize'])
    rounding = 0
    while tick_size < 1:
        tick_size = tick_size * 10
        rounding = rounding + 1
    avg_price = round(avg_price, rounding)
    print('Price:', avg_price)

    # Создаём ордера
    buy_orders = []
    sell_orders = []
    for i in range(1, conf['sell']+1):
        price = avg_price + conf['step']*i
        price = round(price, rounding)
        order = create_order(conf['symbol'], 'SELL', price, conf['volume'], True)
        if order is not False:
            sell_orders.append(order['orderId'])

    for i in range(1, conf['buy']+1):
        price = avg_price - conf['step']*i
        price = round(price, rounding)
        order = create_order(conf['symbol'], 'BUY', price, conf['volume'], True)
        if order is not False:
            buy_orders.append(order['orderId'])

    currency_list[conf['symbol']] = {'step': conf['step'],
                                     'volume': conf['volume'],
                                     'buy': conf['buy'],
                                     'sell': conf['sell'],
                                     'price': avg_price,
                                     'buy_orders': buy_orders,
                                     'sell_orders': sell_orders}
    # print(conf['symbol'], ": ", currency_list[conf['symbol']])
    insert_new_currency(conf['symbol'], currency_list[conf['symbol']])
    send_currency(conf['symbol'], conf['step'], conf['volume'], conf['buy'], conf['sell'])


def update_data_in_table(symbol, data):
    """
    Записывает новые списки ордеров в таблицу
    """
    try:
        buy_orders = str(data['buy_orders'])
        sell_orders = str(data['sell_orders'])
        values = (buy_orders, sell_orders, symbol)
        query = """UPDATE trading
                    SET buy_orders = ?, sell_orders = ?
                    WHERE symbol = ?"""
        cur.execute(query, values)
        conn.commit()
    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite:", error)


def delete_currency(symbol):
    try:
        query = """DELETE FROM trading WHERE symbol=?"""
        cur.execute(query, (symbol, ))
        conn.commit()
    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite:", error)
    else:
        id_orders = currency_list[symbol]['sell_orders'] + currency_list[symbol]['buy_orders']
        try:
            for i in id_orders:
                client.cancel_order(symbol=symbol, orderId=i)
        except Exception as e:
            print("Ошибка сервера - {}".format(e))
        del currency_list[symbol]


def insert_new_currency(symbol, data):
    """
    Добавляем новую запись в таблицу
    """
    try:
        values = (symbol,
                  data['buy'],
                  data['sell'],
                  data['step'],
                  data['volume'],
                  data['price'],
                  str(data['sell_orders']),
                  str(data['buy_orders']))
        query = """INSERT INTO trading VALUES (?, ?, ?, ?, ?, ?, ?, ?)"""
        cur.execute(query, values)
        conn.commit()
    except sqlite3.Error as error:
        print("Ошибка при работе с SQLite:", error)


def process_binance_message(msg):
    """
    Callback для сокета Бинанса.
    Обрабатывает сообщение от сервера
    Структуры сообщений: https://github.com/binance/binance-spot-api-docs/blob/master/user-data-stream.md#order-update
    """
    if msg['e'] == 'executionReport':
        symbol = msg['s']    # Валютная пара
        order_id = msg['i']  # ID ордера
        side = msg['S']      # Продажа или покупка
        price = float(msg['p'])     # Цена

        if msg['X'] == 'FILLED':
            # Если ордер заполнился (завершился)
            if symbol in currency_list:
                # Если пара есть у нас в списке отслеживаний
                currency = currency_list[symbol]
                buy_orders = currency['buy_orders']
                sell_orders = currency['sell_orders']
                if side == 'BUY':
                    # Если завершился ордер на покупку
                    if order_id in buy_orders:
                        buy_orders.remove(order_id)
                        new_price = price + currency['step']
                        # Создаём ордер на продажу с ценой на шаг выше
                        order = create_order(symbol, 'SELL', new_price, currency['volume'], True)
                        if order is not False:
                            sell_orders.append(order['orderId'])
                    else:
                        print("Неизвестный id ордера на покупку")
                elif side == 'SELL':
                    # Если завершился ордер на продажу
                    if order_id in sell_orders:
                        sell_orders.remove(order_id)
                        new_price = price - currency['step']
                        # Создаём ордер на покупку с ценой на шаг ниже
                        order = create_order(symbol, 'BUY', new_price, currency['volume'], True)
                        if order is not False:
                            buy_orders.append(order['orderId'])
                    else:
                        print("Неизвестный id ордера на продажу")

                currency['buy_orders'] = buy_orders
                currency['sell_orders'] = sell_orders
                currency_list[symbol] = currency
                # update_data_in_table(symbol, currency)
                # Кладём команду на обновление таблицы в очередь т.к. сокет крутится в отдельном потоке
                # и не имеет доступа к базе
                queue.put(f"UPDATE {symbol}")
            else:
                print("Неотслеживаемая пара ", symbol)


def read_all_table(name):
    """
    Читаем все записи в таблице и форматируем их в currency_list
    """
    cur.execute(f"""SELECT * from {name}""")
    records = cur.fetchall()
    print("Записей в таблице:", len(records))

    if len(records) == 0:
        return False
    else:
        for row in records:
            symbol = row[0]
            buy = row[1]
            sell = row[2]
            step = row[3]
            volume = row[4]
            price = row[5]
            sell_orders = row[6][1:-1]  # Используем срез чтобы убрать скобки []
            buy_orders = row[7][1:-1]

            # # т.к. sell_orders и buy_orders это списки id ордеров, а в базе они лежат как строки -> распарсим их
            tmp = sell_orders.split(', ')
            sell_orders = []
            for i in tmp:
                if i == '':
                    break
                sell_orders.append(int(i))
            tmp = buy_orders.split(', ')
            buy_orders = []
            for i in tmp:
                if i == '':
                    break
                buy_orders.append(int(i))

            currency_list[symbol] = {'step': step,
                                     'volume': volume,
                                     'buy': buy,
                                     'sell': sell,
                                     'price': price,
                                     'buy_orders': buy_orders,
                                     'sell_orders': sell_orders}
    return True


def continue_work():
    """
    Востановление работы после выключения или краша
    Смотрим, что  стало с нашими ордерами. Создаём новые ордера вместо тех, которые закрылись, пока мы не работали.
    Продолжаем следить за оставшимеся
    """
    print('Востановление работы...')
    for symbol in currency_list:
        settings = currency_list[symbol]
        price = settings['price']
        sell_orders = settings['sell_orders']
        buy_orders = settings['buy_orders']
        buy = settings['buy']
        sell = settings['sell']
        step = settings['step']
        volume = settings['volume']
        print(f"{symbol} цена:{price} шаг:{step} объём:{volume} докупки:{buy} продажи:{sell}")
        # Получаем список открытых ордеров
        id_open_orders = []
        for order in client.get_open_orders(symbol=symbol):
            id_open_orders.append(order['orderId'])
        print("Открытые ордера:", id_open_orders)
        # Отменяем оставшиеся ордера
        for order_id in (sell_orders+buy_orders):
            if order_id in id_open_orders:
                try:
                    client.cancel_order(symbol=symbol, orderId=order_id)
                    # print("Удалён ордер:", symbol, order_id)
                except Exception as e:
                    print("Ошибка сервера - {}".format(e))
            # else:
            #     print(f"Ордер уже закрыт {symbol} {order_id}")
        # Создаём новые ордера с учетом того, что текущая цена может отличаться от указанной в настройках
        current_price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        print("Текущая цена:", current_price)
        new_sell = []
        new_buy = []
        if (price-step) < current_price < (price+step):
            # Если текущая цена находится в пределах цены из настроек
            for i in range(1, sell+1):
                step_price = round((price + step*i), 2)
                order = create_order(symbol, 'SELL', step_price, volume)
                if order is not False:
                    new_sell.append(order['orderId'])
            for i in range(1, buy+1):
                step_price = round((price - step*i), 2)
                order = create_order(symbol, 'BUY', step_price, volume)
                if order is not False:
                    new_buy.append(order['orderId'])
        elif current_price >= (price+step):
            # Если текущая цена находится выше линии S1 (Больше начальнойцена на шаг или более)
            start = 0
            # Делаем проверку - нужно ли нам на саму цену X выставлять ордер.
            if sell == 0:
                start = 1
            for i in range(start, buy+1):
                # Заполним сектор ниже линии Х (Если кол-во ордеров на покупку в настройках >0, то берём ещё и саму X)
                step_price = round((price - step*i), 2)
                order = create_order(symbol, 'BUY', step_price, volume)
                if order is not False:
                    new_buy.append(order['orderId'])
            for i in range(1, sell+1):
                step_price = round((price + step*i), 2)
                # Если цена ушла из канала, то последняя линия остаётся без ордера
                if step_price == round((price + sell*step), 2) and current_price > step_price:
                    break

                if (current_price - step_price) >= step:
                    order = create_order(symbol, 'BUY', step_price, volume)
                    if order is not False:
                        new_buy.append(order['orderId'])
                elif (current_price - step_price) < 0:
                    order = create_order(symbol, 'SELL', step_price, volume)
                    if order is not False:
                        new_sell.append(order['orderId'])
                elif 0 < (current_price - step_price) < step:
                    continue
        elif current_price <= (price-step):
            start = 0
            # Делаем проверку - нужно ли нам на саму цену X выставлять ордер.
            if buy == 0:
                start = 1
            # Если текущая цена находится ниже линии B1 (Меньше начальнойцена на шаг или более)
            for i in range(start, sell+1):
                step_price = round((price + step*i), 2)
                order = create_order(symbol, 'SELL', step_price, volume)
                if order is not False:
                    new_sell.append(order['orderId'])
            for i in range(1, buy+1):
                step_price = round((price - step*i), 2)
                # Если цена ушла из канала, то последняя линия остаётся без ордера
                if step_price == round((price - sell*step), 2) and current_price < step_price:
                    break

                if (step_price - current_price) >= step:
                    order = create_order(symbol, 'SELL', step_price, volume)
                    if order is not False:
                        new_sell.append(order['orderId'])
                elif (step_price - current_price) < 0:
                    order = create_order(symbol, 'BUY', step_price, volume)
                    if order is not False:
                        new_buy.append(order['orderId'])
                elif 0 < (step_price - current_price) < step:
                    continue
        settings['sell_orders'] = new_sell
        settings['buy_orders'] = new_buy
        currency_list[symbol] = settings
        queue.put(f"UPDATE {symbol}")


def processing_console_input():
    while True:
        command = input()
        queue.put(command)


def processing_commands():
    """Обработка команд и работа с БД"""
    while True:
        if queue.empty():
            continue
        else:
            command = queue.get()
            command = command.split()

        if command[0] == 'NEW':
            if len(command) != 6:
                print(f"Ошибка - {command[0]} Неверное количество аргументов.")
                continue
            try:
                currency_config = {'symbol': command[1],
                                   'step': float(command[2]),
                                   'volume': float(command[3]),
                                   'buy': int(command[4]),
                                   'sell': int(command[5])}
                init_trade(currency_config)
            except Exception as e:
                print("Ошибка - {}".format(e))
                continue

        elif command[0] == 'DELETE':
            if len(command) != 2:
                print(f"Ошибка - {command[0]} Неверное количество аргументов.")
                continue
            symbol = command[1]
            if symbol in currency_list:
                delete_currency(symbol)
                print("Удаление завершено")
            else:
                print("Ошибка - Заданной пары нет в списке отслеживаемых.")

        elif command[0] == 'UPDATE':
            if len(command) != 2:
                print(f"Ошибка - {command[0]} Неверное количество аргументов.")
                continue
            symbol = command[1]
            if symbol in currency_list:
                update_data_in_table(symbol, currency_list[symbol])
            else:
                print("Ошибка - Заданной пары нет в списке отслеживаемых.")
        else:
            print("Ошибка - Неизвестная команда.")


def new_client(clnt, serv):
    # print("Новое подключение:", clnt)
    for record in currency_list.keys():
        send_currency(record, currency_list[record]['step'], currency_list[record]['volume'],
                      currency_list[record]['buy'], currency_list[record]['sell'], clnt)


def send_currency(currency, step, volume, buy, sell, client=None):
    """Отправляем пару с настройками во время востановления работы"""
    msg = json.dumps({
        "currency": currency,
        "step": step,
        "volume": volume,
        "buy": buy,
        "sell": sell
    })
    if client is not None:
        server.send_message(client=client, msg=msg)
    else:
        server.send_message_to_all(msg=msg)


def new_message(first, serv, msg):
    print("Client:", msg)
    queue.put(msg)


server = WebsocketServer(host='127.0.0.1', port=7777, loglevel=logging.INFO)
server.set_fn_new_client(new_client)
server.set_fn_message_received(new_message)


def StartServer():
    server.run_forever()


server_thread = Thread(target=StartServer, daemon=True)
server_thread.start()


if __name__ == '__main__':
    cur.execute("""CREATE TABLE IF NOT EXISTS trading(
       symbol TEXT PRIMARY KEY,
       buy INT,
       sell INT,
       step REAL,
       volume REAL,
       price REAL,
       sell_orders TEXT,
       buy_orders TEXT);
    """)

    # Если мы уже работали ранее и выключились/упали,
    # то востанавливаем ордера и настройки из бд и продолжаем за ними следить
    if read_all_table('trading') is True:
        continue_work()

    twm = ThreadedWebsocketManager(api_key=key, api_secret=secret)
    twm.start()
    user_socket = twm.start_user_socket(callback=process_binance_message)

    print("Типы команд:\n"
          "    Добавление новой пары с настройками\n"
          "    1) NEW пара шаг объём кол-во на покупку кол-во на продажу\n"
          "        Пример: NEW DOGERUB 0.1 10 3 3\n"
          "    Удаление существующей пары с настройками\n"
          "    2) DELETE пара\n"
          "        Пример: DELETE DOGERUB")

    # Запускаем оброботчик команд из консоли
    server_thread = Thread(target=processing_console_input, daemon=True)
    server_thread.start()

    path = Path("Grid_front", "index.html")
    webbrowser.open(str(path), new=1)
    processing_commands()
    twm.join()
    print("Завершение программы")
