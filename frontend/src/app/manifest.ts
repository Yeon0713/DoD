import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "도나",
    short_name: "도나",
    description: "사장님이 오늘 할 일을 하나씩 챙겨 드려요",
    start_url: "/",
    display: "standalone",
    background_color: "#fbf7f2",
    theme_color: "#fbf7f2",
    lang: "ko",
    icons: [{ src: "/donna/b4-1.png", sizes: "216x216", type: "image/png" }],
  };
}
