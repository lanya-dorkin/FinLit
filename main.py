import pandas as pd
from alpha_vantage.fundamentaldata import FundamentalData
import streamlit as st
import requests
from bs4 import BeautifulSoup
import random, string


def convert_to_re(df):
    def convert(x):
        try:
            x = int(x)
            q = (len(str(x).replace('-', '')) - 1) // 3 * 3
            if q >= 12:
                return f'{round(x / 10**q, 3)}t'
            if q >= 9:
                return f'{round(x / 10**q, 3)}b' 
            if q >= 6:
                return f'{round(x / 10**q, 3)}m' 
            if q >= 3:
                return f'{round(x / 10**q, 3)}k' 
            if q < 3:
                return f'{round(x / 10**q, 3)}'
        except ValueError:
            return None

    if 'reportedCurrency' in df.index.values:
        df = df.T
        for col in df.drop('reportedCurrency', axis=1).columns:
            df[col] = df[col].apply(convert)
        df = df.T
    else:
        for col in df.columns:
            df[col] = df[col].apply(convert)
    return df

def populate_financials(data, symbol, frame):
    if frame == 'Annual':
        income_statement = data.get_income_statement_annual(symbol)[0]
        income_statement['fiscalDateEnding'] = income_statement['fiscalDateEnding'].apply(lambda x: x.split("-")[0])   
    if frame == 'Quarterly':
        income_statement = data.get_income_statement_quarterly(symbol)[0]
        income_statement['fiscalDateEnding'] = income_statement['fiscalDateEnding'].apply(lambda x: f'{x.split("-")[0]} Q{round(int(x.split("-")[1])/3)}')

    income_statement.set_index('fiscalDateEnding', inplace=True)
    income_statement = income_statement.T

    if frame == 'Annual':
        balance_sheet = data.get_balance_sheet_annual(symbol)[0]
        balance_sheet['fiscalDateEnding'] = balance_sheet['fiscalDateEnding'].apply(lambda x: x.split("-")[0])   
    if frame == 'Quarterly':
        balance_sheet = data.get_balance_sheet_quarterly(symbol)[0]
        balance_sheet['fiscalDateEnding'] = balance_sheet['fiscalDateEnding'].apply(lambda x: f'{x.split("-")[0]} Q{round(int(x.split("-")[1])/3)}')

    balance_sheet.set_index('fiscalDateEnding', inplace=True)
    balance_sheet = balance_sheet.T

    if frame == 'Annual':
        cash_flow = data.get_cash_flow_annual(symbol)[0]
        cash_flow['fiscalDateEnding'] = cash_flow['fiscalDateEnding'].apply(lambda x: x.split("-")[0])   
    if frame == 'Quarterly':
        cash_flow = data.get_cash_flow_quarterly(symbol)[0]
        cash_flow['fiscalDateEnding'] = cash_flow['fiscalDateEnding'].apply(lambda x: f'{x.split("-")[0]} Q{round(int(x.split("-")[1])/3)}')

    cash_flow.set_index('fiscalDateEnding', inplace=True)
    cash_flow = cash_flow.T

    overview = data.get_company_overview(symbol)[0]

    return {'income_statement': income_statement, 'balance_sheet': balance_sheet, 'cash_flow': cash_flow, 'overview': overview}

def formula_to_fields(formula):
    tags = st.session_state.tags_to_fields.keys()
    for t in tags:
        formula = formula.replace(t, f'{st.session_state.tags_to_fields[t]}')
    return formula

def calculate_formula(merged_df, formula, sym):
    tags = merged_df.index
    formulas = pd.Series(dtype='object')
    for col in merged_df.columns:
        formula_ = formula
        for t in tags:
            formula_ = formula_.replace(t, f'{merged_df.loc[t, col]}')
        formulas[col] = formula_

    try:
        res_series = formulas.apply(lambda formu: eval(compile(formu, '', 'eval')))[::-1].rename(sym)
        return res_series
    except NameError as e:
        return f'{str(e).split(" is")[0].replace("name", "tag")} is incorrect, please refer to [Vintage Alpha docs](https://documentation.alphavantage.co/FundamentalDataDocs/gaap_documentation.html) or tables above for the tags'
    except TypeError:
        return f'One of the tags of {sym} has null in financials'
    except SyntaxError:
        return 'The formula is incorrect, perhaps you forgort a sign?'

def collect_tags():
    url = 'https://documentation.alphavantage.co/FundamentalDataDocs/gaap_documentation.html'
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')

    tags = [x.string.strip() for x in soup.find_all('h3')]
    fields = [x.string.strip() for x in soup.find_all('i')]

    tags_to_fields = dict(zip(tags, fields))
    fields_to_tags = dict(zip(fields, tags))
    return tags_to_fields, fields_to_tags

def change_ready():
    st.session_state['ready to show'] = False

def delete_from_session():
    for td in st.session_state.to_delete:
        if td in st.session_state['merged_df'][frame]:
            del st.session_state['merged_df'][frame][td]
        if f'{td}_{frame}' in st.session_state:
            del st.session_state[f'{td}_{frame}']

def get_financials():
    if 'new_symbol' in st.session_state:
        symbol = st.session_state.new_symbol
    else:
        symbol = st.session_state.symbol
    frame = st.session_state.frame
    if f'{symbol}_{frame}' not in st.session_state:
        try:
            s = string.ascii_uppercase + string.digits
            key = ''.join(random.sample(s,16))
            data_feed = FundamentalData(key=key)
            st.session_state[f'{symbol}_{frame}'] = populate_financials(data=data_feed, symbol=symbol, frame=frame)
            if 'merged_df' not in st.session_state:
                st.session_state['merged_df'] = {'Quarterly': {}, 'Annual': {}}
            if symbol not in st.session_state['merged_df'][frame]:
                st.session_state['merged_df'][frame][symbol] = pd.concat([st.session_state[f'{symbol}_{frame}']['income_statement'], 
                                                                          st.session_state[f'{symbol}_{frame}']['balance_sheet'], 
                                                                        st.session_state[f'{symbol}_{frame}']['cash_flow']])
        except ValueError as e:
            if 'Error getting data from the api, no return was given.' in str(e):
                st.warning('The ticker symbol is incorrect')
            if 'Our standard API call frequency is 5 calls per minute and 500 calls per day.' in str(e):
                st.warning('The Alpha Vantage API has a limit of 5 calls per minute and 500 calls per day.\nPlease try again in a second or change the API key')
            # print(str(e))

def convert_tags(df):
    def compare(x):
        if x in st.session_state.tags_to_fields.keys():
            return st.session_state.tags_to_fields[x]
        else:
            return x
    new_index = df.index.to_series().apply(compare)
    return df.set_index(new_index)

def fill_from_common():
    st.session_state.formula = common_formulas[st.session_state.common]

def field_to_formula():
    for i in st.session_state['field']:
        st.session_state['formula'] = st.session_state['formula'] + ' ' + i

def formula_from_multi_tags():
    st.session_state['formula'] = ''
    for i in st.session_state['multi_tags']:
        st.session_state['formula'] = st.session_state['formula'] + ' ' + st.session_state.fields_to_tags[i]
    st.session_state['formula'] = st.session_state['formula'][1:]

def append_key(api_keys):
    if st.session_state.new_api_key in api_keys:
        st.warning('There is such key already')
    else:
        with open("api_keys.txt", "a") as myfile:
            myfile.writelines(st.session_state.new_api_key + '\n')
        
common_formulas = {
    'Working capital': 'totalCurrentAssets - totalCurrentLiabilities',
    'Current ratio': 'totalCurrentAssets / totalCurrentLiabilities',
    'Quick ratio': '(cashAndShortTermInvestments + currentNetReceivables) / totalCurrentLiabilities',
    'Debt to Equity Ratio': 'totalLiabilities / totalShareholderEquity',
    'Debt to Total Assets': 'totalLiabilities / totalAssets',
    'Gross Margin': 'grossProfit / totalRevenue',
    'Profit margin before tax': 'incomeBeforeTax / totalRevenue',
    'Profit margin after tax': 'netIncome / totalRevenue',
    'Earnings Per Share': 'netIncome / commonStockSharesOutstanding',
    'Interest Coverage Ratio': 'ebit / interestExpense'
}


st.title('FinLit dashboard')
if ('tags_to_fields' not in st.session_state) and ('fields_to_tags' not in st.session_state):
    st.session_state.tags_to_fields, st.session_state.fields_to_tags = collect_tags()

st.sidebar.write('Links')
st.sidebar.write('[Telegram](https://t.me/lanyadorkin)')
st.sidebar.write('[Github](https://github.com/lanya-dorkin/FinLit)')

frame = st.radio("Annual or quarterly reports to use", ["Annual", "Quarterly"], key='frame', on_change=change_ready)
st.text_input("Add a ticker symbol, you can do it multiple times", key='new_symbol', on_change=get_financials)
try:
    st.session_state.symbol = st.selectbox('Now you can choose', key='choice', options=list(st.session_state['merged_df'][frame].keys()))
except KeyError:
    pass

if 'symbol' in st.session_state:
    if f'{st.session_state.symbol}_{frame}' in st.session_state:
        with st.expander("Company Overview"):
            for key in st.session_state[f'{st.session_state.symbol}_{frame}']['overview']:
                st.write(key, ': ', st.session_state[f'{st.session_state.symbol}_{frame}']['overview'][key])

        with st.expander("Income Statement"):
            st.dataframe(convert_tags(convert_to_re(st.session_state[f'{st.session_state.symbol}_{frame}']['income_statement'].copy())))
            
        with st.expander("Balance Sheet"):
            st.dataframe(convert_tags(convert_to_re(st.session_state[f'{st.session_state.symbol}_{frame}']['balance_sheet'].copy())))

        with st.expander("Cash Flow"):
            st.dataframe(convert_tags(convert_to_re(st.session_state[f'{st.session_state.symbol}_{frame}']['cash_flow'].copy())))
        
        st.caption('If you hover over the dataframe you can expand it or scroll with your mouse')


    try:
        if st.session_state.symbol in st.session_state['merged_df'][frame]:
            
            col3, col4 = st.columns(2)
            with col3:
                st.selectbox('Choose a common ratio', key='common', options=common_formulas, on_change=fill_from_common)
            with col4:
                st.multiselect('Insert tags to formula by fields', key='multi_tags', options=st.session_state.fields_to_tags, on_change=formula_from_multi_tags)
            formula = st.text_input('or type in your own formula', key='formula')
            st.caption('You can refer to [Vintage Alpha docs](https://documentation.alphavantage.co/FundamentalDataDocs/gaap_documentation.html) or multiselect above for the tags')
            formula_button = st.button('Use the formula')

            if formula_button:
                df_to_plot = []
                series_error = []
                for sym in st.session_state['merged_df'][frame]:
                    r_series = calculate_formula(st.session_state['merged_df'][frame][sym], formula, sym)
                    if type(r_series) != str:
                        df_to_plot.append(r_series)
                    else:
                        series_error.append(r_series)
                st.session_state.df_to_plot = pd.DataFrame(df_to_plot)
                series_error = pd.Series(series_error, dtype='object')
                for e in series_error.unique():
                    st.warning(e)
                if not st.session_state.df_to_plot.empty:
                    st.subheader(formula_to_fields(formula))
                    if float(st.session_state.df_to_plot.copy().iloc[0, :].sum()) < 10000:
                        st.dataframe(st.session_state.df_to_plot.copy())
                    else:
                        st.dataframe(convert_to_re(st.session_state.df_to_plot.copy()))
                    st.line_chart(st.session_state.df_to_plot.T)
                    st.session_state['ready to show'] = True
            else:
                if st.session_state['ready to show']:
                    df_to_plot = []
                    series_error = []
                    for sym in st.session_state['merged_df'][frame]:
                        r_series = calculate_formula(st.session_state['merged_df'][frame][sym], formula, sym)
                        if type(r_series) != str:
                            df_to_plot.append(r_series)
                        else:
                            series_error.append(r_series)
                    st.session_state.df_to_plot = pd.DataFrame(df_to_plot)
                    series_error = pd.Series(series_error, dtype='object')
                    for e in series_error.unique():
                        st.warning(e)
                    if not st.session_state.df_to_plot.empty:
                        st.subheader(formula_to_fields(formula))
                        if float(st.session_state.df_to_plot.copy().iloc[0, :].sum()) < 10000:
                            st.dataframe(st.session_state.df_to_plot.copy())
                        else:
                            st.dataframe(convert_to_re(st.session_state.df_to_plot.copy()))
                        st.line_chart(st.session_state.df_to_plot.T)
                    
            col1, col2 = st.columns(2)
            with col1:
                st.text_input('Add a ticker symbol to compare', on_change=get_financials, key='new_symbol')
                st.caption('In case there is an error and no new symbol has appeared, try clicking the button or check the top of the page')
                st.button('Actual button', key='refresh', on_click=get_financials)           
                    
            with col2:
                options_to_del = list(st.session_state['merged_df'][frame].keys())
                if len(options_to_del) - 1 > 0:
                    st.multiselect('Choose symbols to delete from comparison', key='to_delete', options=options_to_del, on_change=delete_from_session)
                                        
    except KeyError:
        pass