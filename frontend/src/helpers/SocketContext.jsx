import PropTypes from "prop-types";
import { createContext, useEffect, useState } from "react";
import io from "socket.io-client";

const SocketContext = createContext();

const SocketProvider = ({ children }) => {
  const [socket, setSocket] = useState(null);

  useEffect(() => {
    // Always connect to the same origin as the page.
    // - Dev: CRA proxy (ws: true in setupProxy.js) forwards to the backend.
    // - Prod: Traefik routes /api/v1/socket to the backend.
    // This ensures session cookies are sent (same-origin) and avoids
    // cross-origin WebSocket issues.
    //
    // The URL is omitted deliberately: socket.io already defaults to the
    // page's own origin, so passing one derived from `window.location` would
    // only hand the connection target to a value the user can influence.
    const newSocket = io({
      transports: ["websocket"],
      path: "/api/v1/socket",
    });
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
