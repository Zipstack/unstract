import PropTypes from "prop-types";
import { createContext, useEffect, useState } from "react";
import io from "socket.io-client";

import { getBaseUrl } from "./GetStaticData";

const SocketContext = createContext();

const SocketProvider = ({ children }) => {
  const [socket, setSocket] = useState(null);

  useEffect(() => {
    let baseUrl = "";
    const body = {
      transports: ["websocket"],
      path: "/api/v1/socket",
    };
    if (!process.env.NODE_ENV || process.env.NODE_ENV === "development") {
      baseUrl = process.env.REACT_APP_BACKEND_URL;
    } else {
      baseUrl = getBaseUrl();
    }
    const newSocket = io(baseUrl, body);
    setSocket(newSocket);
    // Clean up the socket connection on browser unload
    window.onbeforeunload = () => {
      newSocket.disconnect();
    };
    // Clean up the socket connection on component unmount
    return () => {
      newSocket.disconnect();
    };
  }, []);

  return (
    <SocketContext.Provider value={socket}>{children}</SocketContext.Provider>
  );
};

SocketProvider.propTypes = {
  children: PropTypes.any,
};

export { SocketContext, SocketProvider };
