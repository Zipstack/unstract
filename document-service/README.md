## Document Processor Server

A flask server with the following functionalities:

* Upload a document to the server
* Perform find and replace on the document

### Pre-requisites

#### LibreOffice

Application Should be installed and running in headless mode

```bash
/Applications/LibreOffice.app/Contents/MacOS/soffice --backtrace --headless --nocrashreport --nodefault --nologo --nofirststartwizard --norestore --accept="socket,host=127.0.0.1,port=2002,tcpNoDelay=1;urp;StarOffice.ComponentContext"
```

_Change the application path to suit your requirement. The example is for MacOS_

#### Unoserver

Should be installed on the server. Note that Unoserver installation is not straighforward. Unoserver requires the Python
distribution which is bundled with LibreOffice. The following command can be used to install Unoserver

```bash
/Applications/LibreOffice.app/Contents/Resources/python -m pip install unoserver
```

_Change the application path to suit your requirement. The example is for MacOS. Refer
to <https://github.com/unoconv/unoserver>

### Environment Variables

```bash
REDIS_HOST=redis-15866.c99.us-east-1-4.ec2.cloud.redislabs.com
REDIS_PORT=15866
REDIS_PASSWORD=XXXXXXXXXXXXXXXXXXX
UPLOAD_FOLDER=/tmp/document_service/uploads
PROCESS_FOLDER=/tmp/document_service/processed
LIBREOFFICE_PYTHON=/Applications/LibreOffice.app/Contents/Resources/python
PORT=3000
MAX_FILE_SIZE=31457280
```

### Run in development

```
flask --app "src.unstract.document_service.main:app" run --debug
```

### Nginx Configuration

If we are using Nginx to frontend the server for SSL, make sure `Autherization` and `Content-Length` headers are passed

```nginx
location / {
        proxy_pass http://localhost:3000/;
        proxy_buffering off;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-Host $host;
        proxy_set_header X-Forwarded-Port $server_port;
        proxy_pass_request_headers on;
        client_max_body_size 100M;
        proxy_request_buffering off;
        include proxy_params;
}
```

Thunder collection `thunder-collection_document-service.json` for API testing. `upload` a pdf document, then  hit `find_and_replace` api.
it will generate a pdf document. download it and verify replacement text.

VS Marketplace Link: <https://marketplace.visualstudio.com/items?itemName=rangav.vscode-thunder-client>
