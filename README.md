# EZ Cheap Flights Seeker Backend
Python flask server for getting cheap flights information from Skyscanner.

Full tutorial: https://www.codeastar.com/easy-cheap-flights-seeker-web-app-with-flask-and-react/

## Quick Start
1. Install required library
``` 
$pipenv install
```
2. Set your Skyscanner API key (get it free from Rapid API) 
```
$export SKYSCAN_RAPID_API_KEY=YOUR_KEY   (for Linux/MacOS)
or
>$Env:SKYSCAN_RAPID_API_KEY="YOUR_KEY"   (for Windows PowerShell)
or
>set SKYSCAN_RAPID_API_KEY=YOUR_KEY      (for Windwos command shell)
```
3. Start the Flask server
```
$python main.py
```
