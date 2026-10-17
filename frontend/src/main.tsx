import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./App";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/level.css";
import "./styles/house.css";
import "./styles/log.css";
import "./styles/recorder.css";

const root = document.getElementById("root");
if (root === null) throw new Error("no #root element to mount the board on");

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
