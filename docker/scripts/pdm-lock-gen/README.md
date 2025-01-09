# Generate pdm.lock file

Helps generate pdm's lockfiles by running the command `pdm lock -G :all -v` on all necessary packages and services.

- project root
- `backend`
- `prompt-service`
- `runner`
- `unstract/core`
- `unstract/flags`
- `platform-service`
- `x2text-service`
- `unstract/connectors`
- `unstract/tool-sandbox`

Can be run without any arguments to check for lockfile generation on all necessary packages and services
```shell
./pdm-lock.sh
```

Accepts a list of directories to generate for as command line arguments
```shell
./pdm-lock.sh backend prompt-service
```
