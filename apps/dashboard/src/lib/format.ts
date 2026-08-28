export function formatPaise(paise: number): string {
  if (typeof paise !== "number" || isNaN(paise)) return "₹0.00";
  const rupees = paise / 100;
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
  }).format(rupees);
}

export function formatTime(isoDateString: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(isoDateString));
}
