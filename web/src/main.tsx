import React from "react";
import { createRoot } from "react-dom/client";
import { ConfigProvider, App as AntApp } from "antd";
import zhCN from "antd/locale/zh_CN";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <ConfigProvider
      locale={zhCN}
      theme={{
        token: {
          colorPrimary: "#1677ff",
          borderRadius: 8,
          fontFamily: '"Segoe UI", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif',
          controlHeight: 36,
          fontSize: 14,
          colorText: "#1f2937",
          colorTextSecondary: "#6b7280",
          colorBorder: "#e8ecf1",
          colorBorderSecondary: "#eef2f7",
        },
        components: {
          Card: {
            headerFontSize: 15,
          },
          Form: {
            itemMarginBottom: 16,
          },
        },
      }}
    >
      <AntApp>
        <App />
      </AntApp>
    </ConfigProvider>
  </React.StrictMode>,
);
