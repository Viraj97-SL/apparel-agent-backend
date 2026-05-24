import { UploadOutlined } from "@ant-design/icons";
import { Button, Image, Space } from "antd";
import { useEffect, useRef, useState } from "react";

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    cloudinary: any;
  }
}

interface Props {
  value?: string;
  onChange?: (url: string) => void;
}

export const CloudinaryUpload: React.FC<Props> = ({ value, onChange }) => {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const widgetRef = useRef<any>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const check = () => {
      if (window.cloudinary) { setReady(true); return; }
      setTimeout(check, 300);
    };
    check();
  }, []);

  const open = () => {
    if (!ready) return;
    if (!widgetRef.current) {
      widgetRef.current = window.cloudinary.createUploadWidget(
        {
          cloudName: import.meta.env.VITE_CLOUDINARY_CLOUD_NAME,
          uploadPreset: import.meta.env.VITE_CLOUDINARY_UPLOAD_PRESET,
          folder: "apparel_bot_products",
          multiple: false,
          resourceType: "image",
          cropping: false,
        },
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (_error: any, result: any) => {
          if (!_error && result?.event === "success") {
            onChange?.(result.info.secure_url);
            widgetRef.current = null; // reset so next open picks fresh URL
          }
        }
      );
    }
    widgetRef.current.open();
  };

  return (
    <Space direction="vertical">
      {value && (
        <Image
          src={value}
          alt="Product"
          style={{ maxWidth: 180, borderRadius: 8, border: "1px solid #f0f0f0" }}
          preview={{ src: value }}
        />
      )}
      <Button onClick={open} icon={<UploadOutlined />} disabled={!ready}>
        {value ? "Change Image" : "Upload to Cloudinary"}
      </Button>
      {!ready && <span style={{ fontSize: 12, color: "#999" }}>Loading widget…</span>}
    </Space>
  );
};
