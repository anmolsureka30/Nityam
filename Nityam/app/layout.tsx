import type { Metadata, Viewport } from "next";
import { Bricolage_Grotesque, Instrument_Sans, Gochi_Hand } from "next/font/google";
import "./globals.css";

const bricolage = Bricolage_Grotesque({
  variable: "--font-bricolage",
  subsets: ["latin"],
  weight: ["500", "700", "800"],
});

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const gochiHand = Gochi_Hand({
  variable: "--font-gochi",
  subsets: ["latin"],
  weight: ["400"],
});

export const metadata: Metadata = {
  title: "Nityam",
  description:
    "A personal teacher for every student, built on what their class actually taught today.",
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      className={`${bricolage.variable} ${instrumentSans.variable} ${gochiHand.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
