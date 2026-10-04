"""Fonctions pures du filtrage local et du mode compact (données synthétiques).

    python -m unittest discover -s tests
"""

import json
import unittest

from pennylane_mcp.tools.customer_invoices import (
    _compact_invoice, _is_unpaid, _select, _without_file_url,
)
from pennylane_mcp.tools.quotes import _compact_quote


def inv(num, status, deadline, remaining, paid=False, draft=False, amount="120.0"):
    return {
        "id": sum(map(ord, num)), "invoice_number": num, "label": f"Facture CLIENT - {num}",
        "date": "2026-09-01", "deadline": deadline, "status": status, "paid": paid,
        "draft": draft, "amount": amount, "currency_amount_before_tax": "100.0",
        "remaining_amount_with_tax": remaining,
        "public_file_url": "https://exemple.invalid/f.pdf",
        "customer": {"id": 42, "url": "https://exemple.invalid/customers/42"},
        "invoice_lines": {"url": "https://exemple.invalid/lines"},
        "payments": {"url": "https://exemple.invalid/payments"},
    }


TODAY = "2026-10-02"
DATA = [
    inv("L1", "late", "2026-09-26", "600.0"),
    inv("L2", "late", "2026-02-04", "7920.0"),
    inv("U1", "upcoming", "2026-10-29", "480.0"),
    inv("P1", "paid", "2026-08-01", "0.0", paid=True),
    inv("C1", "cancelled", "2026-05-03", "0.0", paid=True),
    inv("A1", "archived", "2026-01-01", "960.0"),
    inv("D1", "draft", "2026-09-01", "120.0", draft=True),
    inv("AV", "credit_note", "2026-09-24", None, amount="-6600.0"),
]


class Impaye(unittest.TestCase):
    def test_regle(self):
        self.assertEqual([i["invoice_number"] for i in DATA if _is_unpaid(i)], ["L1", "L2", "U1"])

    def test_paid_ne_fait_pas_foi(self):
        # Annulée avec paid=true et payée : jamais impayées ; archivée non payée : exclue.
        self.assertFalse(_is_unpaid(inv("X", "cancelled", TODAY, "0.0", paid=True)))
        self.assertFalse(_is_unpaid(inv("X", "archived", TODAY, "960.0")))

    def test_reste_du_illisible(self):
        self.assertFalse(_is_unpaid(inv("X", "late", TODAY, "n/a")))


class Selection(unittest.TestCase):
    def test_en_retard_trie_par_echeance(self):
        got = _select(DATA, True, TODAY, "deadline")
        self.assertEqual([i["invoice_number"] for i in got], ["L2", "L1"])

    def test_borne_stricte(self):
        got = _select([inv("E", "upcoming", TODAY, "1.0")], True, TODAY, "deadline")
        self.assertEqual(got, [])

    def test_tri_decroissant_et_echeance_absente_en_dernier(self):
        sans = inv("N", "upcoming", None, "1.0")
        got = _select(DATA + [sans], True, None, "-deadline")
        self.assertEqual([i["invoice_number"] for i in got], ["U1", "L1", "L2", "N"])

    def test_statut(self):
        got = _select(DATA, False, None, "deadline", "late")
        self.assertEqual([i["invoice_number"] for i in got], ["L2", "L1"])

    def test_echeance_seule(self):
        got = _select(DATA, False, "2026-03-01", "deadline")
        self.assertEqual([i["invoice_number"] for i in got], ["A1", "L2"])


class Compact(unittest.TestCase):
    def test_champs_et_poids(self):
        c = _compact_invoice(DATA[0])
        self.assertEqual(c["customer_id"], 42)
        self.assertEqual(c["remaining_amount_with_tax"], "600.0")
        text = json.dumps(c, indent=2, ensure_ascii=False)
        self.assertNotIn("http", text)
        self.assertLess(len(text), 450)

    def test_detail_sans_public_file_url(self):
        d = _without_file_url(DATA[0])
        self.assertNotIn("public_file_url", d)
        self.assertIn("invoice_lines", d)

    def test_devis(self):
        q = {"id": 7, "quote_number": "D-1", "status": "pending", "customer": {"id": 42, "url": "x"},
             "public_file_url": "https://exemple.invalid/q.pdf", "invoice_lines": {"url": "x"}}
        c = _compact_quote(q)
        self.assertEqual((c["quote_number"], c["status"], c["customer_id"]), ("D-1", "pending", 42))
        self.assertNotIn("http", json.dumps(c))


if __name__ == "__main__":
    unittest.main()
