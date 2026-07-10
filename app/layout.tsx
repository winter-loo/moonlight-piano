import type { Metadata } from "next";
import { headers } from "next/headers";
import "./globals.css";

export async function generateMetadata(): Promise<Metadata> {
  const requestHeaders = await headers();
  const host = requestHeaders.get("x-forwarded-host") ?? requestHeaders.get("host") ?? "moonlight-piano.local";
  const protocol = requestHeaders.get("x-forwarded-proto") ?? "https";
  const origin = `${protocol}://${host}`;

  return {
  title: "月光琴房｜从零学会梦中的婚礼",
  description: "面向零基础学习者的《梦中的婚礼》钢琴学习路径。",
    metadataBase: new URL(origin),
    openGraph: {
      title: "月光琴房｜从零学会梦中的婚礼",
      description: "30 天，从第一颗音符走向舞台。",
      images: [{ url: `${origin}/og.png`, width: 1200, height: 630, alt: "月光琴房" }],
    },
    twitter: { card: "summary_large_image", title: "月光琴房", images: [`${origin}/og.png`] },
  };
}

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="zh-CN"><body>{children}</body></html>;
}
