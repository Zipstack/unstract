This project was bootstrapped with [Create React App](https://github.com/facebook/create-react-app).

## Steps to setup the frontend in local

### Requirements

NodeJS 16

1. Clone [this repo](https://github.com/Zipstack/unstract) in your machine

   `git clone https://github.com/Zipstack/unstract.git`

2. Navigate to the path `unstract/frontend` and run the following commands

   `npm install`

### Steps to run the setup

   `npm start`

3. Node will automatically run the `localhost:3000` in your browser.
   The page will reload when you make changes.
   You may also see any lint errors in the console.

## Notes

1. Install the Prettier extension in your VSCode editor <https://marketplace.visualstudio.com/items?itemName=esbenp.prettier-vscode>
2. Install the ESLint extension in your VSCode editor <https://marketplace.visualstudio.com/items?itemName=dbaeumer.vscode-eslint>

## Available Scripts

In the project directory, you can run:

### `npm start`

Runs the app in the development mode.\
Open [http://localhost:3000](http://localhost:3000) to view it in your browser.

The page will reload when you make changes.\
You may also see any lint errors in the console.

### `npm test`

Launches the test runner in the interactive watch mode.\
See the section about [running tests](https://facebook.github.io/create-react-app/docs/running-tests) for more information.

### `npm run build`

Builds the app for production to the `build` folder.\
It correctly bundles React in production mode and optimizes the build for the best performance.

The build is minified and the filenames include the hashes.\
Your app is ready to be deployed!

See the section about [deployment](https://facebook.github.io/create-react-app/docs/deployment) for more information.

## React Strict Mode

*React Strict Mode* is enabled by default, which will **mount all components twice** during local development.

This helps in verifying the integrity of the React components, and is in alignment with all the frontend use cases known and envisioned currently.

## Learn More

You can learn more in the [Create React App documentation](https://facebook.github.io/create-react-app/docs/getting-started).

To learn React, check out the [React documentation](https://reactjs.org/).

### Code Splitting

This section has moved here: [https://facebook.github.io/create-react-app/docs/code-splitting](https://facebook.github.io/create-react-app/docs/code-splitting)

### Analyzing the Bundle Size

This section has moved here: [https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size](https://facebook.github.io/create-react-app/docs/analyzing-the-bundle-size)

### Making a Progressive Web App

This section has moved here: [https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app](https://facebook.github.io/create-react-app/docs/making-a-progressive-web-app)

### Advanced Configuration

This section has moved here: [https://facebook.github.io/create-react-app/docs/advanced-configuration](https://facebook.github.io/create-react-app/docs/advanced-configuration)

### Deployment

This section has moved here: [https://facebook.github.io/create-react-app/docs/deployment](https://facebook.github.io/create-react-app/docs/deployment)

### `npm run build` fails to minify

This section has moved here: [https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify](https://facebook.github.io/create-react-app/docs/troubleshooting#npm-run-build-fails-to-minify)

## Dockerization

Dockerizing a project bootstrapped with Create React App (CRA) is a common practice to ensure consistent development and deployment environments. Docker containers provide isolation and portability, making it easier to manage your application's dependencies and run it consistently across different environments.

### Development

Create a Dockerfile.dev for development. This Dockerfile will use Node.js to set up your development environment:

Remember, you need to have your app code and any necessary files in the same directory as this Dockerfile. To build and run the Docker container, you can use the following commands:

```
# Build the Docker image
docker build -t frontend:dev -f Dockerfile.dev .

# Run the Docker container
docker run -it -p 3000:3000 frontend:dev
```

## Production

Create a Dockerfile.prod for production. This Dockerfile will use NGINX to serve your optimized production build:

```
npm ci && npm run build

docker build -t frontend:prod -f Dockerfile.prod .

docker run -p 80:80 frontend:prod
```

If you need a custom NGINX configuration, place it in your project root folder (e.g., nginx.conf) and copy it using the COPY command in Dockerfile.prod.

This approach allows you to have separate Dockerfiles for development and production while keeping them in the root folder of your React app. It helps you maintain a consistent and organized structure for managing different deployment environments.
