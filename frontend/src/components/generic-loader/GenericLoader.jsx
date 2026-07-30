import { Typography } from "@/components/ui/shims/antd-typography";
import { Logo64 } from "../../assets";
import "./GenericLoader.css";

function GenericLoader() {
  return (
    <div className="generic-loader center">
      <div className="spinner-box">
        <Logo64 className="fadeinout" />
        <div className="pulse-container">
          <div className="pulse-bubble pulse-bubble-1"></div>
          <div className="pulse-bubble pulse-bubble-2"></div>
          <div className="pulse-bubble pulse-bubble-3"></div>
          <div className="pulse-bubble pulse-bubble-4"></div>
        </div>
        <Typography>
          Please wait while we prepare your session. <br></br>This might take a
          minute.
        </Typography>
      </div>
    </div>
  );
}

export { GenericLoader };
