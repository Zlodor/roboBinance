class Candle:
    """
    Класс "Cвеча"
    Вмещает ответ от API на запрос "get_klines"
    """

    def __init__(self, candel):
        """
        :param candel: ответ на запрос get_klines
        """
        self.open_time = candel[0]
        self.open = float(candel[1])
        self.high = float(candel[2])
        self.low = float(candel[3])
        self.close = float(candel[4])
        self.volume = float(candel[5])
        self.close_time = candel[6]
        # self.quote_asset_volume = candel[7]
        # self.number_of_trades = candel[8]
        # self.buy_base_asset_volume = candel[9]
        # self.buy_quote_asset_volume = candel[10]
        # self.can_be_ignored = candel[11]
        self.lin_reg = None  # Значение линейной регрессии в этой свече
        self.lin_pos = None  # Значение линейной регрессии в положительной части в этой свече
        self.lin_neg = None  # Значение линейной регрессии в отрицательной части в этой свече
        self.slope = None   # Наклон линии тренда
        self.macd = None
        self.macd_s = None
        self.macd_h = None


class Candlestick:
    """
    Класс "Подсвечник"
    Является списком объектов типа Candle
    """

    def __init__(self):
        self.candles = []  # Список под свечи
        self._len = 0  # Количество элементов

    def __int__(self, candle_list):
        """
        :param candle_list - список Candle
        """
        self.candles = candle_list
        self._len = len(candle_list)

    def append(self, candle: Candle):
        """
        Добавляет свечу к списку
        """
        self.candles.append(candle)
        self._len += 1

    def ToList(self):
        """
        Возвращает имеющийся список свечей
        """
        return self.candles

    def Count(self):
        """
        Возвращает количество элементов
        """
        return self._len

    def GetDataFrame(self):
        """
        Возвращает DataFrame из Pandas
        В него входят: open_time, close (время открытия, цена закрытия)
        """
        import pandas as pd
        data = dict.fromkeys(['Time', 'Close'])
        time = []
        close = []
        for i in self.candles:
            time.append(i.open_time)
            close.append(float(i.close))
        data['Time'] = time
        data['Close'] = close
        df = pd.DataFrame(data)
        df['Time_ms'] = pd.to_datetime(df['Time'], unit='ms')
        return df

    def GetLastDataFrame(self):
        """
        Возвращает DataFrame из Pandas
        В него входят: open_time, close (время открытия, цена закрытия)
        """
        import pandas as pd
        data = dict.fromkeys(['Time', 'Close'])
        time = []
        close = []
        last_candles = self.candles[-34::]
        for i in last_candles:
            time.append(i.open_time)
            close.append(float(i.close))
        data['Time'] = time
        data['Close'] = close
        df = pd.DataFrame(data)
        return df