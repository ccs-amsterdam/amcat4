import ClientProviders from "@/components/Contexts/ClientProviders";
import Navbar from "@/components/Menu/Navbar";
import { Toaster } from "@/components/ui/sonner";
import { Metadata } from "next";
import { Poppins } from "next/font/google";
import "./globals.css";

const font = Poppins({
  subsets: ["latin"],
  weight: ["200", "300", "400", "500", "600", "700", "800"],
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL("http://localhost:3000"),
  title: {
    default: "AmCAT",
    template: "%s | AmCAT",
  },
  description: "Amsterdam Content Analysis Toolkit",

  openGraph: {
    title: "AmCAT",
    description: "Amsterdam Content Analysis Toolkit",
    locale: "en_US",
    type: "website",
  },
  icons: {
    icon: [{ url: "/favicon/favicon.ico" }],
    apple: [{ url: "/favicon/apple-touch-icon.png" }],
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={font.className} suppressHydrationWarning>
      <body className="no-scrollbar relative flex min-h-screen flex-col scroll-smooth ">
        <ClientProviders>
          <Navbar />
          {children}
          <Toaster />
        </ClientProviders>
      </body>
    </html>
  );
}
