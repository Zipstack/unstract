// import React from "react";
import ReactDOM from "react-dom/client";

import { Logo64 } from "./assets";
import { LazyLoader } from "./components/widgets/lazy-loader/LazyLoader.jsx";
import { SocketProvider } from "./helpers/SocketContext.js";
import "./index.css";

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  // <React.StrictMode>

  <SocketProvider>
    <LazyLoader
      loader={
        <div className="center">
          <Logo64 />
        </div>
      }
      component={() => import("./App.jsx")}
      componentName="App"
    />
  </SocketProvider>
  // </React.StrictMode>
);
