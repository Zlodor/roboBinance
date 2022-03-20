import configparser
import math
import numpy as np
import pandas as pd
import pandas_ta as ta
from binance.client import Client
import json
from binance import ThreadedWebsocketManager
from flask import Flask, render_template, request, flash, redirect, jsonify
from flask_cors import CORS
from Candle import Candle, Candlestick
# from threading import Thread
# import logging
# from websocket_server import WebsocketServer
import webbrowser


class RegressionTrend:
    """
    Методы для построения регрессионного тренда
    """
    POSITIVE_RANGE = 2  # Коэффициент для положительного диапозона в регрессионном тренде
    NEGATIVE_RANGE = -2  # Коэффициент для отрицательного диапозона в регрессионном тренде
    pirson = 0.0  # Коэффициент Пирсона при последнем вычислении регрессионного тренда

    @staticmethod
    def _GetCorrelation(x, y):
        """
        Метод вычисления кэффициента Пирсона
        :param x: List of float
        :param y: List of float
        :return: float
        """
        x_mean = sum(x) / len(x)
        y_mean = sum(y) / len(y)
        x_minus_mean = []
        y_minus_mean = []
        x_powed = []
        y_powed = []
        xy = []

        for n in x:
            x_minus_mean.append(n - x_mean)
        for n in y:
            y_minus_mean.append(n - y_mean)
        for n in range(len(x)):
            xy.append(x_minus_mean[n] * y_minus_mean[n])
        for n in x_minus_mean:
            x_powed.append(math.pow(n, 2))
        for n in y_minus_mean:
            y_powed.append(math.pow(n, 2))
        return sum(xy) / math.sqrt(sum(x_powed) * sum(y_powed))

    @staticmethod
    def _GetStandardDeviation(arr):
        """
        Метод вычисления стандартной ошибки
        :param arr: List of float
        :return: float
        """
        mean = sum(arr) / len(arr)
        devs = []
        for n in arr:
            devs.append(math.pow((n - mean), 2))
        return math.sqrt(sum(devs) / (len(arr) - 1))

    @staticmethod
    def Search(candle_list):
        """
        Метод построения линейного регрессионного тренда. Возвращает наклон линии тренда.
        :param candle_list: List of Candle
        :return: float
        """
        X = []  # Список под номера свечей
        Y = []  # Список для цен закрытия свечей
        count = len(candle_list)  # Кол-во элементов в списке

        for n in range(count):
            X.append(n)
            Y.append(float(candle_list[n].close))

        standard_dev_x = RegressionTrend._GetStandardDeviation(X)
        standard_dev_y = RegressionTrend._GetStandardDeviation(Y)
        RegressionTrend.pirson = RegressionTrend._GetCorrelation(X, Y)
        slope = RegressionTrend.pirson * standard_dev_y / standard_dev_x
        deviation = 0.0
        interception = (sum(Y) / count) - slope * (sum(X) / count)

        for n in range(count):
            deviation += math.pow(Y[n] - (interception + slope * n), 2)
        deviation = math.sqrt(deviation / (count - 2))

        n = 0
        for can in candle_list:
            can.lin_reg = interception + slope * n
            can.lin_pos = can.lin_reg + deviation * RegressionTrend.POSITIVE_RANGE
            can.lin_neg = can.lin_reg - deviation * math.fabs(RegressionTrend.NEGATIVE_RANGE)
            can.slope = round(slope, 2)
            n += 1
        return slope


MesadgeList = []  # Список под сообщения о дивергенциях
markers = []  # Список маркеров продажи


def SearchDivirgens(can: Candlestick):
    df = can.GetDataFrame()
    df.ta.macd(close='Close', fast=12, slow=26, signal=9, append=True)
    df.rename(columns={'MACD_12_26_9': 'macd', 'MACDh_12_26_9': 'macd_h', 'MACDs_12_26_9': 'macd_s'}, inplace=True)
    macd_h = df['macd_h'].to_list()
    candle_list = can.ToList()
    MesadgeList.clear()  # Удаляем старые сообщения
    tmp_list = []  # для пара (начало/конец/пирсон) дивергенций, для дальнейшей их склейки
    markers.clear()  # Удаляем прошлые маркеры

    # Разбиваем MACD на промежутки с одинаковыми знаками
    index = 0  # Номер текущего элемента
    count = 0  # Количество записей в словаре
    start = 0  # Начало промежутка
    stop = 0  # Конец промежутка
    gaps = {}  # Словарь с промежутками
    flag = True  # Флаг, что текущий анализируемый период >0
    if macd_h[0] > 0:
        flag = True
    else:
        flag = False

    for m in macd_h:
        if m < 0 and flag is True:
            # Смена знака промежутка на -
            if stop - start >= 5:
                gaps[count] = [start, stop]
                count += 1
                start = index
                stop = index
            flag = False
            index += 1
        elif m > 0 and flag is False:
            # Смена знака промежутка на +
            if stop - start >= 5:
                gaps[count] = [start, stop]
                count += 1
                start = index
                stop = index
            flag = True
            index += 1
        else:
            # Смены знака нет. Смещаем конец промежутка и наращиваем индекс итератора
            stop = index
            index += 1
    if index - start >= 5:
        gaps[count] = [start, index]
        count += 1
    # print("Промежутки: ", gaps)

    for i in range(count):
        # Ищем перегибы(экстремумы) на найденных промежутках
        div = False  # флаг наличия дивергенции
        start = gaps[i][0] + 1
        stop = gaps[i][1] - 1
        extremums = []
        slope = RegressionTrend.Search(candle_list[start - 1: stop + 2])

        if slope > 0:  # Если тренд восходящий -> ищем дивергенцию (цена растёт, macd падает)
            for n in range(start, stop):
                if macd_h[n] > macd_h[n - 1] and macd_h[n] > macd_h[n + 1]:
                    extremums.append(n)
            # print(f"Промежуток №{i} - {len(extremums)} экстремумов; экстремумы - {extremums}")

            if len(extremums) >= 2:
                # Если есть перегибы, то ищем дивергенцию
                start_div = extremums[0]  # начало дивергенции
                max_price = candle_list[extremums[0]].close
                for n in range(1, len(extremums)):
                    current = extremums[n]  # Текущий анализируемый экстремум
                    if macd_h[start_div] > macd_h[current]:
                        if max_price <= candle_list[current].close:
                            div = True
                        else:
                            div = False
                    elif macd_h[start_div] == macd_h[current]:
                        if max_price < candle_list[current].close:
                            div = True
                        else:
                            div = False
                    else:
                        div = False

                    if div and RegressionTrend.pirson >= 0.5:
                        # Если нашли дивергенцию
                        pirson = round(RegressionTrend.pirson, 3)
                        str = f"Дивергенция: [{df['Time_ms'].to_list()[start_div]}, {df['Time_ms'].to_list()[current]}]; Пирсон={pirson}"
                        tmp_list.append([start_div, current, pirson])
                        print(str)
                        # ищем маркеры продажи
                        for i in range(start_div, current):
                            if float(candle_list[i].lin_neg) > float(candle_list[i].low):
                                markers.append({'time': candle_list[i].open_time})
                    # ДЛЯ ОТЛАДКИ
                    # elif not div and RegressionTrend.pirson >= 0.5:
                    #     pirson = round(RegressionTrend.pirson, 3)
                    #     str = f"[{df['Time_ms'].to_list()[start_div]}, {df['Time_ms'].to_list()[current]}]; " \
                    #           f"Пирсон={pirson}; [{max_price}/{candle_list[current].close}], [{macd_h[start_div]}/{macd_h[current]}]"
                    #     print(str)

                    if max_price < candle_list[current].close:
                        max_price = candle_list[current].close
                        start_div = current
        # Если тренд нисходящий -> ищем конвергенции
        # else:

    if len(tmp_list) == 0:
        MesadgeList.append("Дивергенций нет!")
        print("Дивергенций нет!")
    else:
        print("ДО", tmp_list)
        if len(tmp_list) == 1:
            MesadgeList.append(f"Дивергенция: [{df['Time_ms'].to_list()[tmp_list[0][0]]}, "
                               f"{df['Time_ms'].to_list()[tmp_list[0][1]]}]; Пирсон={tmp_list[0][2]}")
        else:
            for i in range(len(tmp_list) - 1):
                n = i + 1
                # for n in range(i+1, len(tmp_list)):
                while n < len(tmp_list):
                    # если конец одной дивергенции совпал с началом следующей -> склеиваем их
                    if tmp_list[i][1] == tmp_list[n][0]:
                        tmp_list[i][1] = tmp_list[n][1]
                        tmp_list[i][2] = (tmp_list[i][2] + tmp_list[n][2]) / 2
                        tmp_list.pop(n)
                    else:
                        break
            for i in tmp_list:
                MesadgeList.append(f"Дивергенция: [{df['Time_ms'].to_list()[i[0]]}, {df['Time_ms'].to_list()[i[1]]}]; "
                                   f"Пирсон={i[2]}")
            print("После", tmp_list)
    df = df.fillna(0)
    return df


app = Flask(__name__)
app.config.from_object(__name__)
CORS(app)

CandleList = []
MacdList = []
candles = Candlestick()


@app.route("/data")
def data():
    """
    Возвращает свечи  и регрессию
    """
    curency = request.args.get('curency')
    interval = request.args.get('interval')
    start = request.args.get('from')
    stop = request.args.get('before')

    candlesticks = client.get_historical_klines(curency, interval, start, stop)
    toFront = {}  # Объект, котторый будет отправлен на фронт
    ohlcv = []  # Данные свечей для фронта

    candles.candles.clear()
    for data in candlesticks:
        candles.append(Candle(data))
        ohlcv.append([
            data[0],
            float(data[1]),
            float(data[2]),
            float(data[3]),
            float(data[4]),
            float(data[5])
        ])

    toFront['ohlcv'] = ohlcv

    df = SearchDivirgens(candles)
    rlist = []
    for can in candles.candles:
        if can.slope is not None:
            if can.slope > 0:
                rlist.append([can.open_time, round(can.lin_neg, 2)])

    toFront['lin_neg'] = rlist
    toFront['mesadges'] = MesadgeList
    toFront['markers'] = markers
    return jsonify(toFront)


@app.route("/")
def index():
    return render_template("index.html")


# def NewClient(client, server):
#     print("Новое подключение")
#
#
# def StartServer():
#     server.run_forever()


# server = WebsocketServer(host='127.0.0.1', port=5679, loglevel=logging.INFO)
# server.set_fn_new_client(NewClient)
# server_thread = Thread(target=StartServer, daemon=True)
# server_thread.start()


# def KlineCallback(msg):
#     global current_klines, candles
#     symbol = msg['s']
#     if current_klines[symbol] is not None and current_klines[symbol]['k']['t'] != msg['k']['t']:
#         pair = current_klines[symbol]['k']
#         print(f"{symbol}: {current_klines[symbol]}")
#         candles.append(Candle([pair['t'], pair['o'], pair['h'], pair['l'], pair['c'], pair['v'], pair['T']]))
#         tmp = candles.GetLastDataFrame()
#         tmp.ta.macd(close='Close', fast=12, slow=26, signal=9, append=True)
#         tmp.rename(columns={'MACD_12_26_9': 'macd', 'MACDh_12_26_9': 'macd_h', 'MACDs_12_26_9': 'macd_s'}, inplace=True)
#         server.send_message_to_all(json.dumps({"kline": {
#             "time": pair['t'] / 1000,
#             "open": pair['o'],
#             "high": pair['h'],
#             "low": pair['l'],
#             "close": pair['c']
#         },
#             "macd": {"time": pair['t'] / 1000, "value": tmp["macd"].to_list()[-1]}}))
#     current_klines[symbol] = msg


if __name__ == '__main__':
    config = configparser.ConfigParser()
    config.read_file(open('Config.cfg'))
    key = config.get('KEY', 'API_KEY')
    secret = config.get('KEY', 'SECRET_KEY')
    client = Client(api_key=key, api_secret=secret)

    webbrowser.open('http://127.0.0.1:5000/', new=1)
    app.run(debug=False)

    client.close_connection()
    print("Stop sockets")
