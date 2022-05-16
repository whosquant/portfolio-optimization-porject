import backtrader as bt
import quantstats
import akshare as ak
import efinance as ef
import pandas as pd
import numpy as np
import os
import matplotlib.pyplot as plt
import run
import sys
import math
import imgkit
from PIL import Image
from scipy import stats
import empyrical as ey
import itertools
import collections
import datetime
import riskfolio as rp
import tradesys as ts

def timeformat(i):
    return datetime.datetime.strptime(i, '%Y-%m-%d').strftime( "%d-%b-%y")

def str2timegap(str1 ='2019年第一季度'):
    year = str1[:4]
    if '一' in str1:
        start_md ='01-01'
        end_md ='03-31'
    if '二' in str1:
        start_md ='04-01'
        end_md ='06-30'
    if '三' in str1:
        start_md ='07-01'
        end_md ='09-30'
    if '四' in str1:
        start_md ='10-01'
        end_md ='12-31'
    startdt = year+'-'+ start_md
    enddt = year+'-'+ end_md
    return [startdt,enddt]

def getquarter(date = '2021-01-01'):
    year = date[:4]
    i = int(date[5:7])
    if i ==1 or i ==2 or i==3:
        quarter = '01-01'
    if i ==4 or i ==5 or i==6:
        quarter = '04-01'
    if i ==7 or i ==8 or i==9:
        quarter = '07-01'
    if i ==10 or i ==11 or i==12:
        quarter = '10-01'
    result = str(year)+'-'+str(quarter)
    return result

df_result1 = pd.read_excel('股票型.xlsx')
df_holdhist = df_result1[['key_0','w_mean_risk','持仓时间']].reset_index()
df_holdhist['time'] = df_holdhist['持仓时间'].apply(str2timegap).apply(lambda x:x[0])#.apply(timeformat)
ticker_names = list(set([alls for alls in df_holdhist['key_0']]))
targets = {ticker: {} for ticker in ticker_names}
for i in range(df_holdhist.shape[0]):
    targets[df_holdhist['key_0'][i]].update({df_holdhist['time'][i]: df_holdhist['w_mean_risk'][i]})


class Strategy(bt.Strategy):
    def __init__(self):
        self.order = True
        self.quarter = '2017-01-01'
        # a = self.broker.getvalue()
        # b = self.broker.getcash()
        # print(a)


    def next(self):
        curdate = str(self.datas[0].datetime.date(0))
        if self.order == False:
            quarter = getquarter(curdate)
            if quarter != self.quarter:
                self.order = True
                self.quarter = quarter
                for d in self.datas:
                    id1 = d.params.dataname[-10:-4]
                    position1 = self.positionsbyname[id1]
                    if position1.size < 0:
                        print(position1.size)
                        print('----------!!!!!!!!!!!!---------------')
                    if position1.size > 0:
                        self.order_target_value(d,target = 0 )
            print(curdate, ' cash:', self.broker.get_cash(), 'value:', self.broker.getvalue())
            return

        if self.order == True:
            b = self.broker.getcash()
            for d in self.datas:
                id1 = d.params.dataname[-10:-4]
                if self.quarter in d.target.keys():
                    buyvalue = (d.target[self.quarter])
                    self.order_target_percent(d,target = d.target[self.quarter])
            self.order = False
            print(curdate, ' cash:', self.broker.get_cash(), 'value:', self.broker.getvalue())
            return





cerebro = bt.Cerebro()
for ticker, target in targets.items():
    dataname_i ='datas/'+str(ticker)+'.csv'
    data = bt.feeds.GenericCSVData(
                                    dataname=dataname_i,
                                    fromdate=datetime.datetime(2017, 1, 1),
                                    todate=datetime.datetime(2021, 6, 30),
                                    nullvalue=0.0,
                                    dtformat=('%Y-%m-%d'),
                                    datetime=1,
                                    high = 2,
                                    low=2,
                                    open=2,
                                    close=2,
                                    volume=-1,
                                    openinterest=-1
                                    )
    data.target = target
    cerebro.adddata(data, name=str(ticker))

cerebro.addanalyzer(bt.analyzers.PyFolio, _name='PyFolio')
cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name = "TA")
cerebro.addanalyzer(bt.analyzers.TimeReturn, _name = "TR")
cerebro.addanalyzer(bt.analyzers.SQN, _name = "SQN")
cerebro.addanalyzer(bt.analyzers.Returns, _name = "Returns")
cerebro.addanalyzer(bt.analyzers.TimeDrawDown, _name = "TimeDrawDown")
cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='SharpeRatio', timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=0.03)
cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name='SharpeRatio_A')
cerebro.addstrategy(Strategy)
cerebro.broker.setcash(1000000)

# Execute
results = cerebro.run()

