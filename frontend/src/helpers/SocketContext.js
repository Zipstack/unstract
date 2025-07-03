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
    if (!import.meta.env.PROD) {
      baseUrl = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
    } else {
      baseUrl = getBaseUrl();
    }

    const newSocket = io(baseUrl, {
      ...body,
      // Add error handling and timeouts
      timeout: 5000,
      autoConnect: false, // Don't auto-connect, we'll handle it manually
    });

    // Try to connect with error handling
    newSocket.on('connect_error', (error) => {
      console.log('Socket.IO connection failed, backend not available:', error.message);
    });

    newSocket.on('disconnect', (reason) => {
      console.log('Socket.IO disconnected:', reason);
    });

    // Only try to connect if we're in development and backend URL is set
    if (!import.meta.env.PROD && import.meta.env.VITE_BACKEND_URL) {
      newSocket.connect();
    }
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
