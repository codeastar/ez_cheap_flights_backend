from flask import Flask, request
from flask_restful import Resource, Api
from flask_cors import CORS
import requests
import os, sys, json, time
from tinydb import TinyDB, Query
from tqdm import tqdm
from datetime import date, timedelta, datetime
import constants

app = Flask(__name__)
api = Api(app)
cors = CORS(app, resources=r'/api/*')

db = TinyDB('skyscanner.json')
Profile = db.table('Profile')
Countries = db.table('Countries')
Airports = db.table('Airports')
Currencies = db.table('Currencies')

ENDPOINT_PREFIX = "https://skyscanner-skyscanner-flight-search-v1.p.rapidapi.com/apiservices/"
MARKET = "US"
CURRENCY = "USD"
SLEEP_BUFFER = 10
FLIGHT_INFO_DAY_RANGE = 1  

def initProfileDB():
  if "SKYSCAN_RAPID_API_KEY" in os.environ:
    API_KEY = os.environ['SKYSCAN_RAPID_API_KEY']   
    Profile.upsert({'api_key':API_KEY}, Query().api_key.exists())
  else: 
    print("Start API search in TinyDB..")
    API_KEY = Profile.search(Query().api_key.exists())  
    if API_KEY == []: 
      sys.exit("No API key found")
    API_KEY = API_KEY[0]['api_key']
  profile_dict = {
    "API_KEY": API_KEY,
  }
  return profile_dict

def handleAPIException(responseText, apiname):
    print(json.dumps(json.loads(responseText), indent=3, sort_keys=True))
    sys.exit(f"API exception on [{apiname}]")

def getCountries(headers):
    country_list = []
    request_start_time = time.time()
    url = ENDPOINT_PREFIX+f"reference/v1.0/countries/en-US"
    response = requests.request("GET", url, headers=headers)
    if response.status_code != 200: handleAPIException(response.text, "getCountries")
    ss_countries = json.loads(response.text)
    Countries.insert_multiple(ss_countries["Countries"])
    ss_countries = ss_countries["Countries"]
    for country in ss_countries:
        country_list.append(country['Name'])    
    return country_list, request_start_time    

def getIataCode(place_string, request_time_list, headers):
    url = ENDPOINT_PREFIX+f"autosuggest/v1.0/{MARKET}/{CURRENCY}/en-US/"
    querystring = {"query":place_string}
    request_start_time = time.time()
    request_time_list.append(request_start_time)
    if (len(request_time_list) % 40 == 0): 
        the_first_request_time = request_time_list[0]
        second_from_1st_request = round(time.time() - the_first_request_time)
        time.sleep(60-second_from_1st_request+SLEEP_BUFFER)
        request_time_list =[]
    response = requests.request("GET", url, headers=headers, params=querystring)
    if response.status_code != 200: handleAPIException(response.text, "getIataCode")
    place_json = json.loads(response.text)    
    for place in place_json["Places"]:
        if ((len(place['PlaceId']) == 7) and (place['CountryName']==place_string)):
            place_dict = {
                "PlaceName": place['PlaceName'],
                "CountryName": place['CountryName'],
                "Iata": place['PlaceId'][:3], 
            }
            Airports.upsert(place_dict, Query().Iata == place['PlaceId'][:3])
    return request_time_list   

def getCurrencies(headers):
  url = ENDPOINT_PREFIX+f"reference/v1.0/currencies"
  response = requests.request("GET", url, headers=headers)
  if response.status_code != 200: handleAPIException(response.text, "getCurrencies")
  currencies_json = json.loads(response.text)
  for element in currencies_json["Currencies"]: 
    currency = {}
    currency["Code"] = element["Code"]
    currency["Symbol"] = element["Symbol"]
    Currencies.upsert(currency, Query().Code == currency["Code"])

def getFlightInfo(headers, market, currency, place_from, place_to, date_depart, date_return, direct_flag):
  url = ENDPOINT_PREFIX+f"browsequotes/v1.0/{market}/{currency}/en-US/{place_from}/{place_to}/{date_depart}/{date_return}"
  #print(f"Url->{url}")    

  date_depart_d_obj= datetime.strptime(date_depart, '%Y-%m-%d').date()
  date_return_d_obj= datetime.strptime(date_return, '%Y-%m-%d').date()
  
  if (date_depart_d_obj > date_return_d_obj):
      cheapquote_dict = {
        "status": constants.OK_TAG,
        "message": "Date not available",
        "depart": date_depart,
        "return": date_return,
      }
      return cheapquote_dict

  #add try catch exception 
  try:
    response = requests.request("GET", url, headers=headers)
    if response.status_code != 200: 
      #print(json.dumps(json.loads(response.text), indent=3, sort_keys=True))
      cheapquote_dict = {
        "status": constants.ERROR_TAG,
        "message": "Error returned from provider",
        "depart": date_depart,
        "return": date_return,
      }
      return cheapquote_dict

    quotes_json = json.loads(response.text)
    #print(f"Returned JSON->{quotes_json}")
    min_price_low = None
    carrier_names = []
    is_direct = "N/A"
    currency_symbol=quotes_json["Currencies"][0]["Symbol"]
    for quote in quotes_json["Quotes"]:
        direct_flight = quote['Direct']
        if (direct_flight==False and direct_flag==True): continue
        min_price_this = quote['MinPrice']     
        if (min_price_low == None or min_price_this < min_price_low):  
            min_price_low = min_price_this
            is_direct = direct_flight
            carrier_id_outbound = quote['OutboundLeg']['CarrierIds']
            carrier_id_inbound = quote['InboundLeg']['CarrierIds']
            carrier_ids = set(carrier_id_outbound + carrier_id_inbound)

    if min_price_low != None: 
        min_price_low = f"{currency_symbol}{min_price_low}"
        for carrier in quotes_json["Carriers"]:
          carrier_id = carrier['CarrierId']
          if carrier_id in carrier_ids:
            carrier_name = carrier['Name']
            carrier_names.append(carrier_name)
            if len(carrier_names) == len(carrier_ids): break

    cheapquote_dict = {
      "status": constants.OK_TAG,
      "price": min_price_low,
      "carriers": carrier_names,
      "is_direct": is_direct,
      "place_from": place_from, 
      "place_to": place_to,
      "depart": date_depart,
      "return": date_return,
    }         

  except requests.exceptions.ConnectionError:
    cheapquote_dict = {
      "status": constants.ERROR_TAG,
      "message": "Connection error",
      "depart": date_depart,
      "return": date_return,
    }

  print(f"Before Return->{cheapquote_dict}")

  return cheapquote_dict  

class MarketsAPI(Resource):
    def get(self):
        return ss_countries

class PlacesAPI(Resource):
    def get(self):
        return ss_airports

class CurrenciesAPI(Resource):
    def get(self):
        return ss_currencies

class flightInfoAPI(Resource):
    def post(self):
        json_data = request.get_json()
        market = json_data['market']
        currency = json_data['currency']
        selected_date_depart = json_data['date_depart']
        selected_date_return = json_data['date_return']
        place_from = json_data['place_from']
        place_to = json_data['place_to']
        direct_flag = json_data['directFlag']
        day_range = FLIGHT_INFO_DAY_RANGE
        if ('day_range' in json_data): day_range = int(json_data['day_range'])
        #print(f"Market: {market}, Currency: {currency}, Departing: {selected_date_depart}, Returning: {selected_date_return}")
        #print(f"From: {place_from}, To: {place_to}, DirectFlight?: {direct_flag}, DayRange: {day_range}")

        dates_depart = [selected_date_depart]
        dates_return = [selected_date_return]
        date_depart = selected_date_depart
        date_return = selected_date_return

        for change_day_minus in range(day_range): #prev N days
          date_depart_d_obj = (datetime.strptime(selected_date_depart, '%Y-%m-%d').date() - timedelta(days=(change_day_minus+1)))
          if (date_depart_d_obj < date.today()): break
          date_depart = date_depart_d_obj.strftime('%Y-%m-%d')
          date_return = (datetime.strptime(selected_date_return, '%Y-%m-%d').date() - timedelta(days=(change_day_minus+1))).strftime('%Y-%m-%d')
          dates_depart.append(date_depart)
          dates_return.append(date_return)

        for change_day_plus in range(day_range):  #do next N days search
          date_depart = (datetime.strptime(selected_date_depart, '%Y-%m-%d').date() + timedelta(days=(change_day_plus+1))).strftime('%Y-%m-%d')
          date_return = (datetime.strptime(selected_date_return, '%Y-%m-%d').date() + timedelta(days=(change_day_plus+1))).strftime('%Y-%m-%d')
          dates_depart.append(date_depart)
          dates_return.append(date_return)

        #sort the dates
        dates_depart.sort(key = lambda date: datetime.strptime(date, '%Y-%m-%d')) 
        dates_return.sort(key = lambda date: datetime.strptime(date, '%Y-%m-%d')) 

        flight_info = []
        for date_depart in dates_depart:
          for date_return in dates_return:
            flight_info.append(getFlightInfo(headers, market, currency, place_from, place_to, date_depart, date_return, direct_flag))

        flight_info_group = {"flight_info_group":flight_info}

        print(flight_info_group)

        return flight_info_group       

initProfileDB()
profile_dict = initProfileDB()  #init our profile
headers = {
    'x-rapidapi-host': "skyscanner-skyscanner-flight-search-v1.p.rapidapi.com",
    'x-rapidapi-key': profile_dict["API_KEY"]
    }
ss_countries = Countries.all()
request_time_list = []
if len(ss_countries) == 0: 
  print("Get country information from Skyscanner API...")
  country_list, request_start_time = getCountries(headers)
  if (request_start_time > 0): request_time_list.append(request_start_time)
  ss_countries = Countries.all()
else:
  country_list = []
  for country in ss_countries:
    country_list.append(country['Name'])    
print("Got country information")

ss_airports = Airports.search(Query().Iata.exists())
if ss_airports == []: 
  print("Get airport information from Skyscanner API...")
  for country in tqdm(country_list):
        request_time_list = getIataCode(country, request_time_list, headers)
  ss_airports = Airports.search(Query().Iata.exists())      
print("Got airport information")

ss_currencies = Currencies.all()
if len(ss_currencies) == 0: 
  print("Get currency information from Skyscanner API...")
  getCurrencies(headers)
  #ss_currencies = Currencies.search(Query())
  ss_currencies = Currencies.all()
print("Got currency information")

api.add_resource(MarketsAPI, '/api/markets')
api.add_resource(CurrenciesAPI, '/api/currencies')
api.add_resource(PlacesAPI, '/api/places')
api.add_resource(flightInfoAPI, '/api/findflight')

if __name__ == '__main__':
    app.run(debug=True)