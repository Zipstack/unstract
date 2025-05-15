import { Result } from "antd";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

function GenericError() {
  const [searchParams] = useSearchParams();
  const [messages, setMessages] = useState({});
  const [id, setId] = useState(null);
  useEffect(() => {
    // Simulating fetching JSON data with key-value pairs
    const jsonData = {
      IDM: {
        title: "Sorry, but this invitation is not meant for you.",
        subtitle:
          "Please contact the organization owner to send you another invite.",
      },
      INF: {
        title: "This invitation is either invalid or has expired.",
        subtitle:
          "Please contact the organization owner to send you another invite.",
      },
      UMM: {
        title: "Sorry, but you seem to be a member of multiple organizations.",
        subtitle: "This is not allowed normally. Please contact support.",
      },
      USF: {
        title: `We're unable to create your account since an account for your organization ${searchParams.get(
          "domain"
        )} already exists.`,
        subtitle:
          "You'll need to contact the admin of your organization's account to get access or you'll need to use a different email address to sign up.",
      },
      USR: {
        title: `Sign-up not allowed.`,
        subtitle:
          "You'll need to contact the admin of your organization's account to get access.",
      },
      INE001: {
        title: `Email not allowed`,
        subtitle: "Disposable emails not allowed.",
      },
      INE002: {
        title: `Invalid Email format`,
        subtitle: "Please give a valid email address",
      },
      INS: {
        title: `Access Denied`,
        subtitle: "Please contact your administrator to request access.",
      },

      // Add more key-value pairs as needed
    };
    const msgId = searchParams.get("code");

    setId(msgId);
    setMessages(jsonData);
  }, []);

  return (
    <Result
      status="403"
      title={
        id && messages[id]
          ? messages[id].title
          : "Hm, you shouldn't see this normally."
      }
      subTitle={
        id && messages[id]
          ? messages[id].subtitle
          : "Please try to login again for accessing your data."
      }
    />
  );
}

export { GenericError };
