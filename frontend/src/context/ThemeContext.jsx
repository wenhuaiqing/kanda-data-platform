import { createContext, useContext, useEffect, useState } from "react";

// Kanda's palette, taken from their public website (kandacare.com.au), for an
// application demo that is not affiliated with them (the sidebar says so).
//
//   maroon  #510C00   their primary: sidebar, hero tiles, primary buttons, the logo
//   orange  #F15623   their secondary: active nav, card rules, one chart series.
//                     Chrome only - never the only signal of a status: badges
//                     always carry their label.
//   rust    #A33A12   a mid tone between the two for links and controls
//                     (6.6:1 on white)
//   creme   #F5F2E9   their page background, warmed slightly here
//   violet  #5847C9   anything the AI agent produced, so "the model said this"
//                     is never confused with "the data says this"

export const light = {
  name: "light",
  bg: "#F7F4EC",
  surface: "#FFFFFF",
  surfaceRaised: "#FBF9F4",
  border: "rgba(81,12,0,0.12)",
  borderBright: "rgba(81,12,0,0.26)",
  accent: "#A33A12",
  accentText: "#FFFFFF",
  accentGlow: "rgba(163,58,18,0.10)",
  accent2: "#5847C9",
  accent2Glow: "rgba(88,71,201,0.10)",
  text: "#2A1C18",
  textMuted: "rgba(42,28,24,0.68)",
  textDim: "rgba(42,28,24,0.36)",

  sidebarBg: "#510C00",
  sidebarText: "rgba(255,255,255,0.80)",
  sidebarActive: "rgba(241,86,35,0.30)",
  sidebarActiveText: "#FFFFFF",
  sidebarBorder: "rgba(255,255,255,0.10)",
  sidebarMark: "#F15623",
  sidebarMuted: "rgba(255,255,255,0.62)",
  sidebarGroup: "rgba(255,255,255,0.48)",

  headerBg: "#FFFFFF",
  headerText: "#2A1C18",
  headerMuted: "rgba(42,28,24,0.64)",
  headerBorder: "rgba(81,12,0,0.12)",
  headerAccent: "#F15623",

  ctaBg: "#510C00",
  ctaText: "#FFFFFF",
  ctaHoverBg: "#A33A12",
  ctaHoverText: "#FFFFFF",

  cardRule: "#F15623",
  tableHead: "#F3EEE4",
  statHeroBg: "#510C00",
  statHeroText: "#FFFFFF",
  statHeroMuted: "rgba(255,255,255,0.74)",
  rowHover: "rgba(81,12,0,0.04)",
  rowDivider: "rgba(81,12,0,0.08)",
  grid: "rgba(81,12,0,0.09)",
  code: "rgba(81,12,0,0.05)",
  series: ["#A33A12", "#F5841F", "#B9A79F", "#2E8A86"],
  status: { good: "#1F7A5A", warning: "#8A6410", serious: "#B4562A", critical: "#B0122B", neutral: "#5F5550", ai: "#5847C9" },
  statusBg: {
    good: "rgba(31,122,90,0.10)", warning: "rgba(227,162,59,0.20)", serious: "rgba(180,86,42,0.12)",
    critical: "rgba(176,18,43,0.09)", neutral: "rgba(81,12,0,0.06)", ai: "rgba(88,71,201,0.10)",
  },
};

export const dark = {
  name: "dark",
  bg: "#18110F",
  surface: "#221815",
  surfaceRaised: "#2B1F1B",
  border: "rgba(245,242,233,0.11)",
  borderBright: "rgba(245,242,233,0.24)",
  accent: "#F4A27E",
  accentText: "#18110F",
  accentGlow: "rgba(244,162,126,0.14)",
  accent2: "#A99BFF",
  accent2Glow: "rgba(169,155,255,0.14)",
  text: "#F2ECE4",
  textMuted: "rgba(242,236,228,0.66)",
  textDim: "rgba(242,236,228,0.32)",

  sidebarBg: "#2E0A03",
  sidebarText: "rgba(242,236,228,0.76)",
  sidebarActive: "rgba(241,86,35,0.28)",
  sidebarActiveText: "#FFFFFF",
  sidebarBorder: "rgba(242,236,228,0.08)",
  sidebarMark: "#F15623",
  sidebarMuted: "rgba(242,236,228,0.56)",
  sidebarGroup: "rgba(242,236,228,0.42)",

  headerBg: "#18110F",
  headerText: "#F2ECE4",
  headerMuted: "rgba(242,236,228,0.62)",
  headerBorder: "rgba(242,236,228,0.09)",
  headerAccent: "#F5841F",

  ctaBg: "#F2ECE4",
  ctaText: "#18110F",
  ctaHoverBg: "#F5841F",
  ctaHoverText: "#18110F",

  cardRule: "#F15623",
  tableHead: "#2B1F1B",
  statHeroBg: "#6B1A08",
  statHeroText: "#FFFFFF",
  statHeroMuted: "rgba(255,255,255,0.80)",
  rowHover: "rgba(242,236,228,0.04)",
  rowDivider: "rgba(242,236,228,0.07)",
  grid: "rgba(242,236,228,0.09)",
  code: "rgba(242,236,228,0.06)",
  series: ["#F4A27E", "#F5841F", "#CFC3BC", "#4FC2BD"],
  status: { good: "#5CCB9F", warning: "#E0BE6E", serious: "#F08A5D", critical: "#FF7A8C", neutral: "#B5AAA4", ai: "#A99BFF" },
  statusBg: {
    good: "rgba(92,203,159,0.14)", warning: "rgba(224,190,110,0.16)", serious: "rgba(240,138,93,0.14)",
    critical: "rgba(255,122,140,0.14)", neutral: "rgba(255,255,255,0.08)", ai: "rgba(169,155,255,0.14)",
  },
};

const Ctx = createContext(null);
const KEY = "kanda_demo_theme";

function initial() {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "dark" || saved === "light") return saved === "dark";
  } catch { /* storage blocked */ }
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-color-scheme: dark)").matches;
}

export function ThemeProvider({ children }) {
  const [isDark, setIsDark] = useState(initial);
  useEffect(() => {
    try { localStorage.setItem(KEY, isDark ? "dark" : "light"); } catch { /* storage blocked */ }
    document.body.style.background = (isDark ? dark : light).bg;
  }, [isDark]);
  return (
    <Ctx.Provider value={{ t: isDark ? dark : light, isDark, toggle: () => setIsDark((v) => !v) }}>
      {children}
    </Ctx.Provider>
  );
}

export function useTheme() {
  return useContext(Ctx);
}
