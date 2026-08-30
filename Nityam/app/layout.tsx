import type { Metadata, Viewport } from "next";
import { Source_Serif_4, Instrument_Sans, IBM_Plex_Mono, Gochi_Hand } from "next/font/google";
import "./globals.css";

/* The app's three families, three jobs (frontend/src/styles/base.css loads
   the same three): serif for anything read as language, sans for interface,
   mono for anything read as data. Bricolage Grotesque used to carry the
   display type here and appears nowhere in the product. */
const sourceSerif = Source_Serif_4({
  variable: "--font-source-serif",
  subsets: ["latin"],
  weight: ["400", "600", "700"],
});

const plexMono = IBM_Plex_Mono({
  variable: "--font-plex-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

const instrumentSans = Instrument_Sans({
  variable: "--font-instrument",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});

/* Kept, and used for exactly one thing: the teacher's hand on the board in
   the hero mock. That is the product's subject, not decoration. */
const gochiHand = Gochi_Hand({
  variable: "--font-gochi",
  subsets: ["latin"],
  weight: ["400"],
});

export const metadata: Metadata = {
  title: "Nityam — a tutor that sat in your class",
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
      className={`${sourceSerif.variable} ${instrumentSans.variable} ${plexMono.variable} ${gochiHand.variable}`}
    >
      <body>{children}</body>
    </html>
  );
}
