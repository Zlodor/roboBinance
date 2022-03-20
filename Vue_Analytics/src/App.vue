<template>
     <div class="row">
      <div class="column" id="bar">
        <div class="element" id="controls">
          <div class="mini_row">
            <label class="lb">От</label>
            <input v-model="from" class=text-field__input type="date" id="from" name="from"/>
          </div>
          <div class="mini_row">
            <label class="lb">До</label>
            <input v-model="before" class=text-field__input type="date" id="before" name="before"/>
          </div>
          <div class="mini_row">
            <label class="lb">Пара</label>
            <input v-model="curency" class=text-field__input type="text" id="curency" name="curency" placeholder="ETHUSDT" />
          </div>
          <select class=sellector id="interval" v-model="interval">
            <option value="15m">15 минут</option>
            <option value="1h">1 час</option>
            <option value="4h">4 часа</option>
            <option value="8h">8 часов</option>
            <option value="1d">1 день</option>
          </select>
          <input class=c-button type="button" id="calculate" value="Посчитать" v-on:click="getData">
        </div>
        <div class="element" id="out">
          <p v-for="(item, i) in mesadges" :key="i">
            {{ item }}
          </p>
        </div>
      </div>
      <div id="charts">
        <trading-vue ref="tradingVue" :data="dc" :overlays="overlays" :extensions="ext" :width="this.width" :height="this.height"
            :title-txt="curency"
            color-back="#fff"
            color-grid="#eee"
            color-text="#333"></trading-vue>
      </div>
    </div>
</template>

<script>
import {TradingVue, DataCube} from 'trading-vue-js'
import Overlays from 'tvjs-overlays'
import XP from 'tvjs-xp'

var data = {} // Текущая информация от сервера (свечи, macd, ...)

export default {
    name: 'App',
    components: { TradingVue },
    methods: 
    {
        onResize() 
        {
            this.width = window.innerWidth * 0.68,
            this.height = window.innerHeight * 0.98
        },
        getData()
        {
            if (this.from != null && this.before != null && this.curency != null)
            {
                let url = new URL('http://127.0.0.1:5000/data')
                url.searchParams.append('curency', this.curency);
                url.searchParams.append('interval', this.interval);
                url.searchParams.append('from', this.from);
                url.searchParams.append('before', this.before);
                
                fetch(url)
                .then((r) => r.json())
                .then((response) => {
                    data = response
                    console.log(data)
                    let ohlcv = data.ohlcv
                    let reg = data.lin_neg
                    this.dc.set('chart.data', ohlcv)
                    this.dc.set('onchart.Reg-dev.data', reg)
                    this.mesadges = data.mesadges
                });
            }
        }
    },
    mounted() 
    {
        window.addEventListener('resize', this.onResize)
    },
    beforeDestroy() 
    {
        window.removeEventListener('resize', this.onResize)
    },
    data() 
    {
        return {
            mesadges: [],
            interval: "1h",
            curency: "ETHRUB",
            from: null,
            before: null,
            ext: Object.values(XP), // Extension
            dc: new DataCube({chart: {type: "Candles", data: []},                                                 // Основной график со свечами
                              onchart: [{type: "Spline", data: [], name: "Reg-dev", settings: {color: "black"}},  // Графие регрессии
                                        {type: "Markers", data: []}],                                             // Метки пересечения ценой линии регрессии
                              offchart: [{name: "MACD 12/26/9", 
                                          type: "MACD", 
                                          data: [], 
                                          settings: {histColors: ["#35a776", "#79e0b3", "#e54150", "#ea969e"]}}]  // MACD
                              }),
            overlays: [Overlays['MACD'], Overlays['Markers']], // Overlay addon
            width: window.innerWidth * 0.68,
            height: window.innerHeight * 0.98,
        }
    }
}
</script>

<style scoped>
    *, *::before, *::after {
    box-sizing: border-box;
  }

.column {
    margin: 5px;
    background-color: #26A69A;
    padding: 10px;
    display: flex;
    flex-direction: column;
  }

.row {
    width: 100%;
    height: 98vh;
    display: flex;
    flex-direction: row;
}

.text-field__input {
    margin: 5px;
    display: block;
    width: 100%;
    height: calc(2.25rem + 2px);
    padding: 0.375rem 0.75rem;
    font-family: inherit;
    font-size: 1rem;
    font-weight: 400;
    line-height: 1.5;
    color: #212529;
    background-color: #fff;
    background-clip: padding-box;
    border: 1px solid #bdbdbd;
    border-radius: 0.25rem;
    transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out;
}

.text-field__label {
  display: block;
  margin-bottom: 0.25rem;
}

#out {
    font-size: 14pt
}
#controls {
    padding: 5px;
    margin-top: 5px;
    border: 1px solid black
}

#bar {
    width: 30%;
    height: 100%;
    font-size: 24px;
}

#charts {
    width: 70%;
    height: 100%;
}

.c-button {
    margin: 5px;
    min-width: fit-content;
    appearance: none;
    border: 0;
    border-radius: 5px;
    background: #fcfcfc;
    color: #212529;
    padding: 8px 16px;
    font-size: 1rem;
  }

.sellector {
    margin: 5px;
    min-width: fit-content;
    border: 0;
    appearance: none;
    border-radius: 5px;
    background: #fcfcfc;
    color: #212529;
    padding: 8px 16px;
    font-size: 1rem;
}

.lb {
    color: #212529;
    padding: 8px 16px;
    font-size: 1rem;
}

.mini_row {
    display: flex;
    flex-direction: row;
}
</style>


