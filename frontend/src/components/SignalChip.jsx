export default function SignalChip({ action, confidence }) {
  return (
    <span className={`badge ${(action || "hold").toLowerCase()}`}>
      <span className="badge-dot" />
      {action}
      <span className="badge-conf">{Math.round((confidence ?? 0) * 100)}%</span>
    </span>
  );
}
