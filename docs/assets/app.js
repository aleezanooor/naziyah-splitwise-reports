import React, { useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  ArrowDownToLine,
  CircleDollarSign,
  FileJson,
  Landmark,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Upload,
  UsersRound
} from "lucide-react";

const h = React.createElement;

const sampleData = {
  exported_at: "2026-06-27T14:58:00Z",
  owner_name: "Aleeza",
  balances: [
    { from: "Aleeza", to: "Zikra", amount: 42.75, currency: "USD" },
    { from: "Aleeza", to: "Mariam", amount: 18.4, currency: "USD" },
    { from: "Samira", to: "Aleeza", amount: 9.2, currency: "USD" }
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
    },
    {
      id: 1003,
      description: "Taxi to event",
      date: "2026-06-18T21:40:00Z",
      category: "Transportation",
      group_name: "Friends",
      paid_by: "Aleeza",
      cost: { currency_code: "USD", amount: "18.40" },
      shares: [
        { name: "Aleeza", paid_share: "18.40", owed_share: "9.20", net_balance: "9.20" },
        { name: "Samira", paid_share: "0.00", owed_share: "9.20", net_balance: "-9.20" }
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

function icon(Component, size = 18) {
  return h(Component, { size, "aria-hidden": true });
}

function App() {
  const [data, setData] = useState(sampleData);
  const [query, setQuery] = useState("");
  const fileInput = useRef(null);

  const peopleToPay = useMemo(
    () => data.balances.filter((balance) => balance.from === data.owner_name && balance.amount > 0.005),
    [data]
  );

  const peopleWhoOweYou = useMemo(
    () => data.balances.filter((balance) => balance.to === data.owner_name && balance.amount > 0.005),
    [data]
  );

  const totalOutstanding = useMemo(
    () => peopleToPay.reduce((total, balance) => total + balance.amount, 0),
    [peopleToPay]
  );

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

  const visibleTotal = useMemo(
    () => filteredExpenses.reduce((total, expense) => total + Number(expense.cost.amount || 0), 0),
    [filteredExpenses]
  );

  async function importJson(file) {
    const imported = JSON.parse(await file.text());
    if (!Array.isArray(imported.balances) || !Array.isArray(imported.expenses)) {
      throw new Error("That file does not look like a Splitwise report export.");
    }
    setData(imported);
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
        h("p", { className: "eyebrow" }, icon(Sparkles, 16), "Splitwise connector"),
        h("h1", { id: "dashboard-title" }, "Naziyah Splitwise Reports"),
        h(
          "p",
          { className: "lede" },
          "A clean private dashboard for who you owe, who owes you, how much, what it was for, and which expenses created the balance."
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
      h(Metric, { iconNode: icon(CircleDollarSign, 20), label: "You currently owe", value: money(totalOutstanding, peopleToPay[0]?.currency ?? "USD") }),
      h(Metric, { iconNode: icon(UsersRound, 20), label: "People to settle with", value: peopleToPay.length.toString() }),
      h(Metric, { iconNode: icon(Landmark, 20), label: "People owing you", value: peopleWhoOweYou.length.toString() }),
      h(Metric, {
        iconNode: icon(RefreshCw, 20),
        label: "Exported",
        value: new Date(data.exported_at).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
      })
    ),
    h(
      "section",
      { className: "layout" },
      h(SettlementPanel, { title: "Who to pay", kicker: "Settlement plan", balances: peopleToPay }),
      h(
        "section",
        { className: "expense-panel", "aria-labelledby": "expenses-title" },
        h(
          "div",
          { className: "toolbar" },
          h("div", null, h("p", { className: "kicker" }, "Expense trail"), h("h2", { id: "expenses-title" }, "What the balances are for")),
          h("label", { className: "search" }, icon(Search), h("input", {
            value: query,
            onChange: (event) => setQuery(event.target.value),
            placeholder: "Search food, rent, people..."
          }))
        ),
        h("div", { className: "total-strip" }, icon(FileJson), h("span", null, `${money(visibleTotal)} across the visible expense list`)),
        h(
          "div",
          { className: "expense-list" },
          filteredExpenses.map((expense) => h(ExpenseRow, { key: expense.id, expense }))
        )
      ),
      h(SettlementPanel, { title: "Who owes you", kicker: "Incoming", balances: peopleWhoOweYou })
    )
  );
}

function Metric({ iconNode, label, value }) {
  return h("article", { className: "metric" }, h("div", { className: "metric-icon" }, iconNode), h("p", null, label), h("strong", null, value));
}

function SettlementPanel({ title, kicker, balances }) {
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
              h("div", null, h("p", { className: "person" }, balance.to), h("p", { className: "detail" }, `${balance.from} pays ${balance.to}`)),
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
        h("span", null, new Date(expense.date).toLocaleDateString("en-US", { month: "short", day: "numeric" }))
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
