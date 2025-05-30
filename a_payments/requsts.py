import requests
url = "https://api.chapa.co/v1/banks"
payload = ''
headers = {
    'Authorization': 'Bearer CHASECK_TEST-onXVRWu3IzQmNvqpXc0TBzzJhsMl20ET'
}
    
response = requests.get(url, headers=headers, data=payload)
data = response.text
print(data)