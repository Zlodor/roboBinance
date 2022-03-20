from threading import Thread
from binance.client import Client
import json
import sys
from binance import ThreadedWebsocketManager
import logging
from websocket_server import WebsocketServer


def open_config():
    with open("config.json", "r") as read_file:
        data = json.load(read_file)
    assert isinstance(data, object), 'В файле config.json ошибка. Проверьте правильность синтоксиса.'
    return data


class CurrencyPair:
    """
    Класс вылютной пары.
    Список pair содержит экземпляры ранее созданных валютных пар (key: название пары; data: объект CurrencyPait для этой пары)
    При создании новой пары, она попадает в список pairs.
    """
    pairs = {}  # валютные пары, которые уже созданы

    def __init__(self, pair_name, info):
        """
        :param pair_name: название валютной пары (например BNBRUB)
        :param info: JSON ответ на запрос get_symbol_info, содержащий всю информация по паре
        _name: название пары
        _orders: список открытых ордеров по данной паре (key: id ордера на местер аккаунте; data: id ордеров-клонов)
        """
        self._name = pair_name
        self._orders = {}
        self.pairs[pair_name] = self
        self.symbol_ifo = info

    def AddOrder(self, master_id, sattelites_id):
        self._orders[master_id] = sattelites_id
        print(self._orders)

    def OrderExists(self, order):
        return order in self._orders

    def DeleteOrder(self, order):
        del self._orders[order]

    def GetName(self):
        return self._name

    def GetInfo(self):
        return self.symbol_ifo

    def GetOrdersList(self, id):
        return self._orders.get(id)


temp = 0


def NewClient(client, server):
    global temp
    print("Новое подключение")
    server.send_message_to_all(json.dumps({
        "satellites": temp
    }))


def NewOrderToFront(order_id, currency, type, mast, sat):
    server.send_message_to_all(json.dumps({
        "id": order_id,
        "currency": currency,
        "type": type,
        "master": mast,
        "satellites": sat
    }))


def CancelOrderToFront(order_id, currency):
    server.send_message_to_all(json.dumps({
        "id": order_id,
        "currency": currency,
        "type": "CANCEL",
    }))


server = WebsocketServer(host='192.168.1.126', port=5678, loglevel=logging.INFO)
server.set_fn_new_client(NewClient)


def StartServer():
    server.run_forever()


server_thread = Thread(target=StartServer)
server_thread.start()


def main():
    global temp
    config = open_config()
    master_key = config["Master"]["api_key"]
    master_secret = config["Master"]["api_secret"]
    satellites = config["Satellites"]
    number_of_satellites = len(satellites)
    temp = number_of_satellites
    satellite_clients = []  # Список клиентов сателитов
    pairs = []  # список CurrencyPair (список валютных пар с открытыми для них ордерами)

    for num in range(number_of_satellites):
        satellite_clients.append(
            Client(api_key=satellites[num]['api_key'],
                   api_secret=satellites[num]['api_secret']))

    master_client = Client(api_key=master_key,
                           api_secret=master_secret)

    # orders = satellite_clients[0].get_open_orders(symbol='ARPARUB')
    # print("Ордеров:", len(orders))
    # print(satellite_clients[0].get_asset_balance('RUB'))
    # print(satellite_clients[0].get_asset_balance('ARPA'))
    # if len(orders) > 0:
    #     for order in orders:
    #         satellite_clients[0].cancel_order(symbol=order['symbol'], orderId=order['orderId'])
    #         print("Удалён ордер:", order['orderId'])
    #     print(satellite_clients[0].get_asset_balance('RUB'))

    def satellites_cancel_orders(symbol, id):
        current_pair = CurrencyPair.pairs.get(symbol)
        orders_list = current_pair.GetOrdersList(id)
        for num in range(number_of_satellites):
            if orders_list[num] is not None:
                try:
                    satellite_clients[num].cancel_order(symbol=symbol, orderId=orders_list[num])
                    print("     Доп. аккаунт №", num + 1, "удалён ордер:", symbol, orders_list[num])
                except Exception as e:
                    print("     Ошибка - {}".format(e))

    def satellites_create_order(msg, percent, val, pair_info):
        new_sattelites_orders = []  # список под новые ордера сателитов
        quantity_in_orders = []  # Список с количеством валюты в ордерах сателитов
        for sat in satellite_clients:
            balance = float(satellite_clients[0].get_asset_balance(val)['free'])
            if msg['S'] == 'BUY':
                quantity = balance * (percent / 100) / float(msg['p'])
            elif msg['S'] == 'SELL':
                quantity = balance * (percent / 100)
            else:
                print("     Неизвестный тип операции")
                return
            # округляем количество валюты по stepSize
            stepSize = float(pair_info['filters'][2]['stepSize'])
            if stepSize >= 1.0:
                quantity_rounded = round(quantity, 0)
            else:
                count = 0
                while stepSize < 1:
                    stepSize = stepSize * 10
                    count = count + 1
                quantity_rounded = round(quantity, count)
            # print("Баланс:", balance, val, "процент:", percent, "квота:", quantity_rounded)
            try:
                order = sat.create_order(
                    symbol=msg['s'],
                    side=msg['S'],
                    type=msg['o'],
                    timeInForce=msg['f'],
                    quantity=quantity_rounded,
                    price=msg['p'])
                print('     Создан ордер:', order['symbol'], order['orderId'])
                new_sattelites_orders.append(order['orderId'])
                quantity_in_orders.append(quantity_rounded)
            except Exception as e:
                print("     Ошибка - {}".format(e))
                new_sattelites_orders.append(None)
                quantity_in_orders.append(None)
        return {"id": new_sattelites_orders, "quantity": quantity_in_orders}

    def process_user_data(msg):
        if msg['e'] == 'executionReport':
            # Если пришла информация о ходе торгов существующего ордера, то скипаем её
            if msg['x'] == 'TRADE':
                return
            # Если валютная пара ранее не встречалась, то добавляем её
            symbol = msg['s']
            if not msg['s'] in CurrencyPair.pairs:
                print("Добавляем новую валютную пару:", symbol)
                info = master_client.get_symbol_info(symbol)
                pairs.append(CurrencyPair(symbol, info))
            current_pair = CurrencyPair.pairs.get(symbol)
            if msg['x'] == 'NEW':
                print("Пришел новый ордер:", msg['s'], msg['S'], msg['i'])
                # взависимости от  типа операции (BUY/SELL) смотрим разные счета (по base валюте или quote)
                if msg['S'] == 'BUY':
                    vault = current_pair.GetInfo()['quoteAsset']
                    # print("     Валюта, которая тратится:", vault)
                    free_balance = float(master_client.get_asset_balance(vault)['free'])
                    spend = float(msg['p']) * float(msg['q'])
                    percent = spend / ((free_balance + spend) / 100)
                elif msg['S'] == 'SELL':
                    vault = current_pair.GetInfo()['baseAsset']
                    free_balance = float(master_client.get_asset_balance(vault)['free'])
                    spend = float(msg['q'])
                    percent = spend / ((free_balance + spend) / 100)
                pair_info = current_pair.GetInfo()
                new_satellites_orders = satellites_create_order(msg, percent, vault, pair_info)
                current_pair.AddOrder(msg['i'], new_satellites_orders.get("id"))
                NewOrderToFront(msg['i'], symbol, "BUY", msg['q'], new_satellites_orders.get("quantity"))
            # Если пришла отмена ордера
            elif msg['x'] == 'CANCELED':
                print("Пришла отмена ордера:", msg['s'], msg['i'])
                # Если ордер был в нашей базе (навсякий случий это проверим. Может быть это старый ордер,
                # клона которого нет у сателитов)
                if current_pair.OrderExists(msg['i']):
                    CancelOrderToFront(msg['i'], msg['s'])
                    satellites_cancel_orders(msg['s'], msg['i'])

    twm = ThreadedWebsocketManager(api_key=master_key, api_secret=master_secret)
    twm.start()
    user_socket = twm.start_user_socket(callback=process_user_data)
    print("__________Start user's socket__________")

    twm.join()
    print("Terminate program", flush=True)
    twm.stop()


if __name__ == '__main__':
    main()
