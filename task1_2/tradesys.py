# 交易系统，封装回测、优化基本过程


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




# 设置显示环境
def init_display():
    pd.set_option('display.max_rows', None)
    pd.set_option('display.max_columns', None)
    np.set_printoptions(threshold = sys.maxsize)
    plt.rcParams['font.sans-serif'] = ['SimHei']
    
    

    
# 策略类基类
class Strategy(bt.Strategy):
    def __init__(self):
        pass
        
    def log(self, txt, dt = None):
        if self.params.bprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))
                
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            return
        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log("交易被拒绝/现金不足/取消")
        elif order.status in [order.Completed]: 
            if order.isbuy(): 
                self.log('买单执行,%s, %.2f, %i' % (order.data._name, order.executed.price, order.executed.size))
            elif order.issell(): 
                self.log('卖单执行, %s, %.2f, %i' % (order.data._name, order.executed.price, order.executed.size))
        self.order = None
        
    def notify_trade(self, trade): 
        if trade.isclosed: 
            self.log('毛收益 %0.2f, 扣佣后收益 % 0.2f, 佣金 %.2f, 市值 %.2f, 现金 %.2f'%(trade.pnl, trade.pnlcomm, trade.commission, self.broker.getvalue(), self.broker.getcash()))
                
    def stop(self):
        for i, d in enumerate(self.datas):
            pos = self.getposition(d).size
            if pos != 0:
                # print("关闭", d._name)
                self.close()
                
    # 交易数量取整
    def downcast(self, amount, lot): 
        return abs(amount//lot*lot)
        
    # 判断是否是最后的交易日
    def is_lastday(self,data): 
        try: 
            next_next_close = data.close[2]
        except IndexError: 
            return True 
        except: 
            print("发生其它错误")
            return False
            
            
# 回测类
class BackTest():
    """
        A股股票策略回测类
        strategy   回测策略
        codes      回测股票代码列表
        start_date 回测开始日期
        end_date   回测结束日期
        bk_code    基准股票代码
        rf         无风险收益率
        start_cash 初始资金
        stamp_duty 印花税率，单向征收
        commission 佣金费率，双向征收
        adjust     股票数据复权方式，qfq或hfq
        period     股票数据周期(日周月)
        refresh    是否更新数据
        bprint     是否输出中间结果
        bdraw      是否作图
        **param   策略参数，用于调参
    """
    def __init__(self, strategy, codes, start_date, end_date, bk_code = "000300", rf = 0.03, start_cash = 10000000, stamp_duty=0.005, commission=0.0001, adjust = "hfq", period = "daily", refresh = False, bprint = False, bdraw = False, **param):
        self._cerebro = bt.Cerebro()
        self._strategy = strategy
        self._codes = codes
        self._bk_code = bk_code
        self._start_date = start_date
        self._end_date = end_date
        # self._stock_data = stock_data
        # self._bk_data = bk_data
        self._rf = rf
        self._start_cash = start_cash
        self._comminfo = CNA_Commission(stamp_duty=0.005, commission=0.0001)
        self._adjust = adjust
        self._period = period
        self._refresh = refresh
        self._bprint = bprint
        self._bdraw = bdraw
        self._param = param
        
    # 回测前准备
    def _before_test(self):
        for code in self._codes:
            data = get_data(code = code, 
        start_date = self._start_date, 
        end_date = self._end_date,adjust = self._adjust, period = self._period, 
        refresh = self._refresh)
            data = self._datatransform(data, code)
            self._cerebro.adddata(data, name = code)
        self._cerebro.addstrategy(self._strategy, bprint = self._bprint, **self._param)
        self._cerebro.broker.setcash(self._start_cash)
        self._cerebro.broker.addcommissioninfo(self._comminfo)
        
    # 数据转换
    def _datatransform(self, stock_data, code):
        # 生成datafeed
        data = bt.feeds.PandasData(
            dataname=stock_data,
            name=code,
            fromdate=stock_data.日期[0],
            todate=stock_data.日期[len(stock_data) - 1],
            datetime='日期',
            open='开盘',
            high='最高',
            low='最低',    
            close='收盘',
            volume='成交量',
            openinterest=-1
            )
        return data
    
    # 增加分析器
    def _add_analyzer(self):
        self._cerebro.addanalyzer(bt.analyzers.PyFolio, _name='PyFolio')
        self._cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name = "TA")
        self._cerebro.addanalyzer(bt.analyzers.TimeReturn, _name = "TR")
        self._cerebro.addanalyzer(bt.analyzers.SQN, _name = "SQN")
        self._cerebro.addanalyzer(bt.analyzers.Returns, _name = "Returns")
        self._cerebro.addanalyzer(bt.analyzers.TimeDrawDown, _name = "TimeDrawDown")
        self._cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name='SharpeRatio', timeframe=bt.TimeFrame.Days, annualize=True, riskfreerate=self._rf)
        self._cerebro.addanalyzer(bt.analyzers.SharpeRatio_A, _name='SharpeRatio_A')
        self._cerebro.addanalyzer(CostAnalyzer, _name="Cost")
        
    # 运行回测
    def run(self):
        self._before_test()
        self._add_analyzer()
        self._results = self._cerebro.run()
        results = self._get_results()
        results = results[results.index != "股票代码"]
        return results
        
    # 获取回测结果
    def _get_results(self):
        # 计算基准策略收益率
        self._bk_data = get_data(code = self._bk_code, start_date = self._start_date, end_date = self._end_date, refresh = self._refresh)
        bk_ret = self._bk_data.收盘.pct_change()
        bk_ret.fillna(0.0, inplace = True)
    
        if self._bdraw:
            self._cerebro.plot(style = "candlestick",iplot=False)
            print(os.getcwd())
            plt.savefig("E:/code/zinan/trade_strategy/output/" +"backtest_result.jpg")
    
        testresults = self._backtest_result(self._results, bk_ret, rf = self._rf)
        end_value = self._cerebro.broker.getvalue()
        pnl = end_value - self._start_cash

        testresults["初始资金"] = self._start_cash
        testresults["回测开始日期"] = self._start_date
        testresults["回测结束日期"] = self._end_date
        testresults["期末净值"] = end_value
        testresults["净收益"] = pnl
        try:
            testresults["收益成本比"] = pnl/testresults["交易成本"]
        except ZeroDivisionError:
            pass
        testresults["股票代码"] = self._codes
        return testresults
        
    # 计算回测指标
    def _backtest_result(self, results, bk_ret, rf = 0.01):
        # 计算回测指标
        portfolio_stats = results[0].analyzers.getbyname('PyFolio')
        returns, positions, transactions, gross_lev = portfolio_stats.get_pf_items()
        returns.index = returns.index.tz_convert(None)
        totalTrade = results[0].analyzers.getbyname("TA").get_analysis()
        sqn = results[0].analyzers.SQN.get_analysis()["sqn"]
        Returns = results[0].analyzers.Returns.get_analysis()
        timedrawdown = results[0].analyzers.TimeDrawDown.get_analysis()
        sharpe = results[0].analyzers.SharpeRatio.get_analysis()
        sharpeA = results[0].analyzers.SharpeRatio_A.get_analysis()
        cost = results[0].analyzers.Cost.get_analysis()
        
        backtest_results = pd.Series()

        backtest_results["总收益率"] = Returns["rtot"]
        backtest_results["平均收益率"] = Returns["ravg"]
        backtest_results["年化收益率"] = Returns["rnorm"]
        backtest_results["交易成本"] = cost
        backtest_results["SQN"] = sqn
        try:
            backtest_results["交易总次数"] = totalTrade["total"]["total"]
            backtest_results["盈利交易次数"] = totalTrade["won"]["total"]
            backtest_results["盈利交易总盈利"] = totalTrade["won"]["pnl"]["total"]
            backtest_results["盈利交易平均盈利"] = totalTrade["won"]["pnl"]["average"]
            backtest_results["盈利交易最大盈利"] = totalTrade["won"]["pnl"]["max"]
            backtest_results["亏损交易次数"] = totalTrade["lost"]["total"]
            backtest_results["亏损交易总亏损"] = totalTrade["lost"]["pnl"]["total"]
            backtest_results["亏损交易平均亏损"] = totalTrade["lost"]["pnl"]["average"]
            backtest_results["亏损交易最大亏损"] = totalTrade["lost"]["pnl"]["max"]
            
            # 胜率就是成功率，例如投入十次，七次盈利，三次亏损，胜率就是70%。
            # 防止被零除 
            if totalTrade["total"]["total"] == 0: 
                backtest_results["胜率"] = np.NaN 
            else:
                backtest_results["胜率"] = totalTrade["won"]["total"]/totalTrade["total"]["total"]
            # 赔率是指盈亏比，例如平均每次盈利30%，平均每次亏损10%，盈亏比就是3倍。
            # 防止被零除
            if totalTrade["lost"]["pnl"]["average"] == 0:
                backtest_results["赔率"] = np.NaN
            else:
                backtest_results["赔率"] = totalTrade["won"]["pnl"]["average"]/abs(totalTrade["lost"]["pnl"]["average"])
            # 计算风险指标
            self._risk_analyze(backtest_results, returns, bk_ret, rf = rf)
        except KeyError:
            pass
            
        return backtest_results
        
    # 将风险分析和绘图部分提出来
    def _risk_analyze(self, backtest_results, returns, bk_ret, rf = 0.01):
        prepare_returns = False # 已经是收益率序列数据了，不用再转换了
        # 计算夏普比率
        if returns.std() == 0.0:
            sharpe = 0.0
        else:
            sharpe = quantstats.stats.sharpe(returns = returns, rf = rf)
        # 计算αβ值
        alphabeta = quantstats.stats.greeks(returns, bk_ret, prepare_returns = prepare_returns)
        # 计算信息比率
        info = quantstats.stats.information_ratio(returns, bk_ret, prepare_returns = prepare_returns)
        # 索提比率
        sortino = quantstats.stats.sortino(returns = returns, rf = rf)
        # 调整索提比率
        adjust_st = quantstats.stats.adjusted_sortino(returns = returns, rf = rf)
        # skew值
        skew = quantstats.stats.skew(returns = returns, prepare_returns = prepare_returns)
        # calmar值
        calmar = quantstats.stats.calmar(returns = returns, prepare_returns = prepare_returns)
        # r2值
        r2 = quantstats.stats.r_squared(returns, bk_ret, prepare_returns = prepare_returns)
        backtest_results["波动率"] = quantstats.stats.volatility(returns = returns, prepare_returns = prepare_returns)
        backtest_results["赢钱概率"] = quantstats.stats.win_rate(returns = returns, prepare_returns = prepare_returns)
        backtest_results["收益风险比"] = quantstats.stats.risk_return_ratio(returns = returns, prepare_returns = prepare_returns)
        backtest_results["夏普比率"] = sharpe
        backtest_results["α值"] = alphabeta.alpha
        backtest_results["β值"] = alphabeta.beta
        backtest_results["信息比例"] = info
        backtest_results["索提比例"] = sortino
        backtest_results["调整索提比例"] = adjust_st
        backtest_results["skew值"] = skew
        backtest_results["calmar值"] = calmar
        backtest_results["r2值"] = r2
    
        # 最大回撤
        md = quantstats.stats.max_drawdown(prices = returns)
        backtest_results["最大回撤"] = md
    
    
            

if __name__ == "__main__":
    pass