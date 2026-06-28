import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  CalendarDays,
  CircleDollarSign,
  FileJson,
  ReceiptText,
  Search,
  ShieldCheck,
  Upload,
  UsersRound
} from "lucide-react";

const h = React.createElement;
const AUTH_HASH = "bf591c84835b78691448993da7fcb09602508040f14084d8d71fe4421bbc3667";
const REFRESH_INTERVAL_MS = 60_000;
const DATA_SOURCES = [
  { url: "./splitwise-export.live.json", label: "Live Splitwise export" },
  { url: "./splitwise-export.local.json", label: "Local Splitwise export" }
];

const sampleData = {
  exported_at: "2026-06-27T14:58:00Z",
  owner_name: "Aleeza",
  balances: [
    {
      from: "Aleeza",
      to: "Zikra",
      amount: 42.75,
      currency: "USD",
      expense_trail: [
        {
          expense_id: 1001,
          description: "Dinner after meeting",
          date: "2026-06-22T19:20:00Z",
          category: "Dining out",
          group_name: "Household",
          paid_by: "Zikra",
          amount: 33.75,
          currency: "USD",
          owner_paid_share: "0.00",
          owner_owed_share: "33.75",
          friend_name: "Zikra",
          friend_paid_share: "67.50",
          friend_owed_share: "33.75"
        },
        {
          expense_id: 1004,
          description: "Cleaning supplies",
          date: "2026-06-19T12:00:00Z",
          category: "Household supplies",
          group_name: "Apartment",
          paid_by: "Zikra",
          amount: 9,
          currency: "USD",
          owner_paid_share: "0.00",
          owner_owed_share: "9.00",
          friend_name: "Zikra",
          friend_paid_share: "18.00",
          friend_owed_share: "9.00"
        }
      ]
    },
    {
      from: "Aleeza",
      to: "Mariam",
      amount: 18.4,
      currency: "USD",
      expense_trail: [
        {
          expense_id: 1002,
          description: "Groceries",
          date: "2026-06-20T15:05:00Z",
          category: "Groceries",
          group_name: "Apartment",
          paid_by: "Mariam",
          amount: 18.4,
          currency: "USD",
          owner_paid_share: "0.00",
          owner_owed_share: "18.40",
          friend_name: "Mariam",
          friend_paid_share: "55.20",
          friend_owed_share: "18.40"
        }
      ]
    },
    { from: "Samira", to: "Aleeza", amount: 9.2, currency: "USD", expense_trail: [] }
  ],
  expenses: [
    {
      id: 1001,
      description: "Dinner after meeting",
      date: "2026-06-22T19:20:00Z",
      category: "Dining out",
      group_name: "Household",
      paid_by: "Zikra",
      cost: { currency_code: "USD", amount: "67.50" },
      shares: [
        { name: "Aleeza", paid_share: "0.00", owed_share: "33.75", net_balance: "-33.75" },
        { name: "Zikra", paid_share: "67.50", owed_share: "33.75", net_balance: "33.75" }
      ]
    },
    {
      id: 1002,
      description: "Groceries",
      date: "2026-06-20T15:05:00Z",
      category: "Groceries",
      group_name: "Apartment",
      paid_by: "Mariam",
      cost: { currency_code: "USD", amount: "55.20" },
      shares: [
        { name: "Aleeza", paid_share: "0.00", owed_share: "18.40", net_balance: "-18.40" },
        { name: "Mariam", paid_share: "55.20", owed_share: "18.40", net_balance: "36.80" },
        { name: "Samira", paid_share: "0.00", owed_share: "18.40", net_balance: "-18.40" }
      ]
    }
  ]
};

function money(amount, currency = "USD") {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2
  }).format(Number(amount || 0));
}

function shortDate(value) {
  if (!value) return "No date";
  return new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function icon(Component, size = 18) {
  return h(Component, { size, "aria-hidden": true });
}

async function sha256(value) {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

function App() {
  const [data, setData] = useState(sampleData);
  const [sourceLabel, setSourceLabel] = useState("Sample data");
  const [isAuthed, setIsAuthed] = useState(() => sessionStorage.getItem("splitwise-auth") === AUTH_HASH);
  const [query, setQuery] = useState("");
  const fileInput = useRef(null);

  useEffect(() => {
    if (!isAuthed) return undefined;

    let cancelled = false;

    async function loadLatest() {
      for (const source of DATA_SOURCES) {
        try {
          const response = await fetch(`${source.url}?t=${Date.now()}`, { cache: "no-store" });
          if (!response.ok) continue;
          const remoteData = await response.json();
          if (Array.isArray(remoteData.balances) && Array.isArray(remoteData.expenses)) {
            if (!cancelled) {
              setData(remoteData);
              setSourceLabel(source.label);
            }
            return;
          }
        } catch {
          // Try the next source, then stay on sample data if none are available.
        }
      }
    }

    loadLatest();
    const timer = setInterval(loadLatest, REFRESH_INTERVAL_MS);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [isAuthed]);

  const peopleToPay = useMemo(
    () => data.balances.filter((balance) => balance.from === data.owner_name && balance.amount > 0.005),
    [data]
  );

  const peopleWhoOweYou = useMemo(
    () => data.balances.filter((balance) => balance.to === data.owner_name && balance.amount > 0.005),
    [data]
  );

  const totalsByCurrency = useMemo(() => {
    return peopleToPay.reduce((totals, balance) => {
      totals[balance.currency] = (totals[balance.currency] || 0) + Number(balance.amount || 0);
      return totals;
    }, {});
  }, [peopleToPay]);

  const totalLabel = Object.entries(totalsByCurrency)
    .map(([currency, amount]) => money(amount, currency))
    .join(" + ") || money(0);

  const filteredExpenses = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return data.expenses;

    return data.expenses.filter((expense) =>
      [
        expense.description,
        expense.category,
        expense.group_name,
        expense.paid_by,
        ...expense.shares.map((share) => share.name)
      ]
        .join(" ")
        .toLowerCase()
        .includes(normalized)
    );
  }, [data.expenses, query]);

  async function importJson(file) {
    const imported = JSON.parse(await file.text());
    if (!Array.isArray(imported.balances) || !Array.isArray(imported.expenses)) {
      throw new Error("That file does not look like a Splitwise report export.");
    }
    setData(imported);
    setSourceLabel(file.name);
  }

  if (!isAuthed) {
    return h(AuthGate, { onUnlock: () => setIsAuthed(true) });
  }

  return h(
    "main",
    { className: "shell" },
    h(
      "section",
      { className: "hero", "aria-labelledby": "dashboard-title" },
      h(
        "div",
        null,
        h("p", { className: "eyebrow" }, icon(ShieldCheck, 16), sourceLabel),
        h("h1", { id: "dashboard-title" }, "What Aleeza needs to pay"),
        h(
          "p",
          { className: "lede" },
          "A focused settlement dashboard showing who gets paid, how much, and the expense trail behind each balance."
        )
      ),
      h(
        "div",
        { className: "hero-actions" },
        h("input", {
          ref: fileInput,
          className: "visually-hidden",
          type: "file",
          accept: "application/json,.json",
          onChange: (event) => {
            const file = event.target.files?.[0];
            if (!file) return;
            importJson(file).catch((error) => alert(error.message || "Could not import file."));
          }
        }),
        h("button", { type: "button", onClick: () => fileInput.current?.click() }, icon(Upload), "Import export"),
        h("a", { className: "button ghost", href: "./splitwise-sample-export.json", download: true }, icon(ArrowDownToLine), "Sample JSON")
      )
    ),
    h(
      "section",
      { className: "stats", "aria-label": "Summary" },
      h(Metric, { iconNode: icon(CircleDollarSign, 20), label: "You currently owe", value: totalLabel }),
      h(Metric, { iconNode: icon(UsersRound, 20), label: "People to pay", value: peopleToPay.length.toString() }),
      h(Metric, { iconNode: icon(ReceiptText, 20), label: "Expenses loaded", value: data.expenses.length.toString() }),
      h(Metric, { iconNode: icon(CalendarDays, 20), label: "Exported", value: shortDate(data.exported_at) })
    ),
    h(
      "section",
      { className: "payables", "aria-labelledby": "payables-title" },
      h("div", { className: "section-heading" }, h("div", null, h("p", { className: "kicker" }, "Settlement plan"), h("h2", { id: "payables-title" }, "Who to pay and why"))),
      peopleToPay.length
        ? h("div", { className: "payable-grid" }, peopleToPay.map((balance) => h(PayableCard, { key: `${balance.to}-${balance.currency}`, balance })))
        : h("p", { className: "empty" }, "Nothing to settle right now.")
    ),
    h(
      "section",
      { className: "layout" },
      h(SettlementPanel, { title: "Who owes you", kicker: "Incoming", balances: peopleWhoOweYou, ownerName: data.owner_name }),
      h(
        "section",
        { className: "expense-panel", "aria-labelledby": "expenses-title" },
        h(
          "div",
          { className: "toolbar" },
          h("div", null, h("p", { className: "kicker" }, "Expense trail"), h("h2", { id: "expenses-title" }, "All imported expenses")),
          h("label", { className: "search" }, icon(Search), h("input", {
            value: query,
            onChange: (event) => setQuery(event.target.value),
            placeholder: "Search food, rent, people..."
          }))
        ),
        h("div", { className: "total-strip" }, icon(FileJson), h("span", null, `${filteredExpenses.length} visible expenses from this export`)),
        h(
          "div",
          { className: "expense-list" },
          filteredExpenses.length
            ? filteredExpenses.map((expense) => h(ExpenseRow, { key: expense.id, expense }))
            : h("p", { className: "empty" }, "No expenses match that search.")
        )
      )
    )
  );
}

function AuthGate({ onUnlock }) {
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState("");

  async function submit(event) {
    event.preventDefault();
    const hash = await sha256(passcode);
    if (hash === AUTH_HASH) {
      sessionStorage.setItem("splitwise-auth", hash);
      onUnlock();
      return;
    }
    setError("That passcode did not match.");
  }

  return h(
    "main",
    { className: "auth-shell" },
    h(
      "form",
      { className: "auth-panel", onSubmit: submit },
      h("p", { className: "eyebrow" }, icon(ShieldCheck, 16), "Private dashboard"),
      h("h1", null, "Naziyah Splitwise Reports"),
      h("p", { className: "lede" }, "Enter the dashboard passcode to view the latest settlement report."),
      h("label", { className: "auth-field" }, "Passcode", h("input", {
        type: "password",
        value: passcode,
        autoComplete: "current-password",
        onChange: (event) => {
          setPasscode(event.target.value);
          setError("");
        }
      })),
      error ? h("p", { className: "auth-error" }, error) : null,
      h("button", { type: "submit" }, icon(ShieldCheck), "Unlock")
    )
  );
}

function Metric({ iconNode, label, value }) {
  return h("article", { className: "metric" }, h("div", { className: "metric-icon" }, iconNode), h("p", null, label), h("strong", null, value));
}

function PayableCard({ balance }) {
  const trail = balance.expense_trail || [];
  const trailTotal = trail.reduce((total, item) => total + Number(item.amount || 0), 0);
  const unexplained = Math.max(0, Number(balance.amount || 0) - trailTotal);

  return h(
    "article",
    { className: "payable-card" },
    h(
      "header",
      { className: "payable-header" },
      h("div", null, h("p", { className: "kicker" }, "Pay"), h("h3", null, balance.to)),
      h("strong", null, money(balance.amount, balance.currency))
    ),
    h(
      "div",
      { className: "why-list" },
      trail.length
        ? trail.map((item) => h(WhyRow, { key: `${balance.to}-${item.expense_id}-${item.amount}`, item }))
        : h("p", { className: "empty" }, "No matching recent expense trail was found in this export.")
    ),
    unexplained > 0.005
      ? h("p", { className: "trail-note" }, `${money(unexplained, balance.currency)} is from older expenses, settlements, or items outside the imported range.`)
      : null
  );
}

function WhyRow({ item }) {
  return h(
    "div",
    { className: "why-row" },
    h(
      "div",
      null,
      h("p", { className: "why-title" }, item.description),
      h("p", { className: "detail" }, `${shortDate(item.date)} · ${item.group_name} · ${item.category} · paid by ${item.paid_by}`)
    ),
    h("strong", null, money(item.amount, item.currency))
  );
}

function SettlementPanel({ title, kicker, balances, ownerName }) {
  return h(
    "aside",
    { className: "settlement-panel" },
    h("div", { className: "section-heading" }, h("div", null, h("p", { className: "kicker" }, kicker), h("h2", null, title)), icon(ShieldCheck, 22)),
    h(
      "div",
      { className: "payment-list" },
      balances.length
        ? balances.map((balance) =>
            h(
              "article",
              { className: "payment-row", key: `${balance.from}-${balance.to}-${balance.amount}` },
              h("div", null, h("p", { className: "person" }, balance.from === ownerName ? balance.to : balance.from), h("p", { className: "detail" }, `${balance.from} pays ${balance.to}`)),
              h("strong", null, money(balance.amount, balance.currency))
            )
          )
        : h("p", { className: "empty" }, "Nothing to settle here.")
    )
  );
}

function ExpenseRow({ expense }) {
  return h(
    "article",
    { className: "expense-row" },
    h(
      "div",
      { className: "expense-main" },
      h(
        "div",
        null,
        h("p", { className: "expense-title" }, expense.description),
        h("p", { className: "detail" }, `${expense.group_name} · ${expense.category} · paid by ${expense.paid_by}`)
      ),
      h(
        "div",
        { className: "expense-amount" },
        h("strong", null, money(expense.cost.amount, expense.cost.currency_code)),
        h("span", null, shortDate(expense.date))
      )
    ),
    h(
      "div",
      { className: "share-grid" },
      expense.shares.map((share) =>
        h("div", { className: "share", key: `${expense.id}-${share.name}` }, h("span", null, share.name), h("strong", null, money(share.net_balance, expense.cost.currency_code)))
      )
    )
  );
}

createRoot(document.getElementById("root")).render(h(App));
