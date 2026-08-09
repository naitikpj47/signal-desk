// Formatting helpers + chart color tokens.
// CSS variables resolve inside inline SVG, so charts stay in sync with styles.css.
export const chart = {
  green: "var(--green)",
  red: "var(--red)",
  amber: "var(--amber)",
  blue: "var(--blue)",
  dim: "var(--text-3)",
};

export const fmt = (n, digits = 2) =>
  (n ?? 0).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export const signClass = (v) => (v >= 0 ? "pos" : "neg");
