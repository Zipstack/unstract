# x2text-service

Flask service to act as bridge to https://github.com/Unstructured-IO/unstructured-api

The Flask service consists 3 APi's

- Test Connection - Validates the configured url and api key of unstructured io  API

```
curl --location 'http://{host}:{port}/api/v1/x2text/test-connection' \
--header 'accept: application/json' \
--header 'Authorization: Bearer <platform-key>' \
--form 'unstructured-url="https://api.unstructured.io/general/v0/general"' \
--form 'file=@"/home/johny/Documents/test_resume.pdf"' \
--form 'unstructured-api-key="<api-key>"'  

```

api-key will empty in case of community edition

```
Response samples:
status code : 200
{
    "message": "Test connection sucessful"
}
status code : 401
{
    "detail": "API key is malformed, please type the API key correctly in the header."
}
```


- Process Document - Takes in the the unstructed document and convert the same to text and download it as text file

```
curl --location 'http://{host}:{port}/api/v1/x2text/process' \
--header 'accept: application/json' \
--header 'Authorization: <platform-key>' \
--form 'unstructured-api-key="<api-key>"' \
--form 'unstructured-url="https://api.unstructured.io/general/v0/general"' \
--form 'file=@"/home/johny/Documents/test_resume1.pdf"


```

- Health - API to check if the falsk service is up and running
```
curl --location 'http://{host}:{port}/api/v1/x2text/health'

Response samples:
status code : 200
OK
```
