import { Route, BrowserRouter as Router, Routes } from "react-router-dom";

import "./App.css";
import { ErrorPage } from "./components/error-page/Error.jsx";
import { AppLayout } from "./components/layout/AppLayout.jsx";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" exact element={<AppLayout />} />
        <Route path="/error" element={<ErrorPage />} />
      </Routes>
    </Router>
  );
}

export default App;
