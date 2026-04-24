import React from "react";
import ReactDOM from "react-dom/client";
import App from "./App";
import "./index.css"; // <-- DÒNG NÀY LÀ QUAN TRỌNG NHẤT, NÓ NẠP TAILWIND VÀO

ReactDOM.createRoot(document.getElementById("root") as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);