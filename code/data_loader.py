"""
Data loader: reads all CSV files and builds lookup indexes for fast access.
"""
import os
import csv
from collections import defaultdict
from config import DATASET_DIR


def _read_csv(filename):
    """Read a CSV file from the dataset directory and return list of dicts."""
    path = os.path.join(DATASET_DIR, filename)
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


class DataStore:
    """Central data store with pre-built indexes for all dataset tables."""

    def __init__(self):
        # ─── Raw tables ──────────────────────────────────────────────────
        self.messages = _read_csv("messages.csv")
        self.sample_messages = _read_csv("sample_messages.csv")
        self.users_raw = _read_csv("users.csv")
        self.groups_raw = _read_csv("groups.csv")
        self.group_members_raw = _read_csv("group_members.csv")
        self.business_accounts_raw = _read_csv("business_accounts.csv")
        self.user_business_history_raw = _read_csv("user_business_history.csv")
        self.message_history_raw = _read_csv("message_history.csv")
        self.message_events_raw = _read_csv("message_events.csv")
        self.daily_notification_raw = _read_csv("daily_notification_summary.csv")
        self.images_raw = _read_csv("images.csv")
        self.voice_notes_raw = _read_csv("voice_notes.csv")

        # ─── Build indexes ───────────────────────────────────────────────
        self._build_indexes()

    def _build_indexes(self):
        # User lookup
        self.users = {}
        for u in self.users_raw:
            uid = u["user_id"]
            self.users[uid] = {
                "user_id": uid,
                "dnd_window": u["do_not_disturb_window"],
                "opened_30d": int(u["messages_opened_30d"]),
                "replied_30d": int(u["messages_replied_30d"]),
                "dismissed_30d": int(u["notifications_dismissed_30d"]),
                "reported_30d": int(u["messages_reported_30d"]),
            }

        # Group lookup
        self.groups = {}
        for g in self.groups_raw:
            gid = g["group_id"]
            self.groups[gid] = {
                "group_id": gid,
                "group_name": g["group_name"],
                "group_type": g["group_type"],
                "member_count": int(g["member_count"]),
                "admin_count": int(g["admin_count"]),
                "messages_30d": int(g["messages_30d"]),
            }

        # Group membership lookup: (user_id, group_id) → membership
        self.memberships = {}
        for gm in self.group_members_raw:
            key = (gm["user_id"], gm["group_id"])
            self.memberships[key] = {
                "role": gm["role"],
                "messages_sent_30d": int(gm["messages_sent_30d"]),
                "messages_read_30d": int(gm["messages_read_30d"]),
                "replies_sent_30d": int(gm["replies_sent_30d"]),
                "dismissed_30d": int(gm["notifications_dismissed_30d"]),
                "group_muted": int(gm["group_muted_by_user"]) == 1,
            }

        # Also index: which groups does a sender belong to? (for checking admin status)
        self.sender_memberships = defaultdict(dict)
        for gm in self.group_members_raw:
            self.sender_memberships[gm["user_id"]][gm["group_id"]] = gm["role"]

        # Business account lookup
        self.businesses = {}
        for b in self.business_accounts_raw:
            bid = b["business_id"]
            official = b.get("official_domain", "") or ""
            sender_domain = b.get("domain_used_by_sender", "") or ""
            self.businesses[bid] = {
                "business_id": bid,
                "display_name": b["display_name"],
                "brand_name": b["brand_name"],
                "category": b["category"],
                "verified": int(b["verified"]) == 1,
                "official_domain": official,
                "sender_domain": sender_domain,
                "domain_mismatch": bool(official and sender_domain and
                                        official.lower() != sender_domain.lower()),
                "account_age_days": int(b["account_age_days"]),
                "messages_sent_30d": int(b["messages_sent_30d"]),
                "reports_30d": int(b["user_reports_30d"]),
                "sender_domain_age": int(b.get("domain_used_by_sender_age_days", 0) or 0),
            }

        # User-business relationship lookup: (user_id, business_id) → relationship
        self.user_business = {}
        for ub in self.user_business_history_raw:
            key = (ub["user_id"], ub["business_id"])
            opted_out_at = ub.get("promotions_opted_out_at", "") or ""
            self.user_business[key] = {
                "why": ub["why_user_knows_account"],
                "last_activity": ub.get("last_activity_at", ""),
                "allows_promotions": int(ub.get("allows_promotions", 0) or 0) == 1,
                "opted_out": bool(opted_out_at),
                "opted_out_at": opted_out_at,
                "activity_count_180d": int(ub.get("activity_count_180d", 0) or 0),
                "msgs_opened_30d": int(ub.get("messages_opened_30d", 0) or 0),
                "msgs_dismissed_30d": int(ub.get("messages_dismissed_30d", 0) or 0),
                "msgs_replied_30d": int(ub.get("messages_replied_30d", 0) or 0),
            }

        # Message history indexes
        self.history_by_user = defaultdict(list)
        self.history_by_sender = defaultdict(list)
        self.history_by_business = defaultdict(list)
        self.history_by_group = defaultdict(list)
        self.history_by_id = {}
        self.all_history_ids = set()

        for mh in self.message_history_raw:
            mid = mh["message_id"]
            uid = mh["user_id"]
            self.history_by_id[mid] = mh
            self.all_history_ids.add(mid)
            self.history_by_user[uid].append(mh)

            sender = mh.get("sender_user_id", "") or ""
            if sender:
                self.history_by_sender[(uid, sender)].append(mh)

            biz = mh.get("business_id", "") or ""
            if biz:
                self.history_by_business[(uid, biz)].append(mh)

            grp = mh.get("group_id", "") or ""
            if grp:
                self.history_by_group[(uid, grp)].append(mh)

        # Message events lookup: message_id → event
        self.events_by_message = {}
        for ev in self.message_events_raw:
            mid = ev["message_id"]
            self.events_by_message[mid] = {
                "user_id": ev["user_id"],
                "opened": int(ev.get("message_opened", 0) or 0) == 1,
                "replied": int(ev.get("message_replied", 0) or 0) == 1,
                "reaction_time": ev.get("reaction_time_minutes", ""),
                "dismissed": int(ev.get("notification_dismissed", 0) or 0) == 1,
                "muted_after": int(ev.get("muted_after_message", 0) or 0) == 1,
                "reported": int(ev.get("message_reported", 0) or 0) == 1,
            }

        # Daily notification summary: user_id → list of daily records
        self.daily_notifications = defaultdict(list)
        for dn in self.daily_notification_raw:
            uid = dn["user_id"]
            self.daily_notifications[uid].append({
                "date": dn["date"],
                "sent": int(dn["notifications_sent"]),
                "dismissed": int(dn["notifications_dismissed"]),
            })

        # Image and voice note lookups
        self.images = {img["image_id"]: img["file_path"] for img in self.images_raw}
        self.voice_notes = {vn["voice_note_id"]: vn["file_path"] for vn in self.voice_notes_raw}

        # Sample messages for evaluation (indexed by message_id)
        self.sample_labels = {}
        for sm in self.sample_messages:
            self.sample_labels[sm["message_id"]] = {
                "action": sm["action"],
                "message_type": sm["message_type"],
                "reason": sm["reason"],
                "confidence": float(sm["confidence"]),
                "evidence": sm["evidence_message_ids"],
            }

    def get_user(self, user_id):
        return self.users.get(user_id, None)

    def get_group(self, group_id):
        if not group_id:
            return None
        return self.groups.get(group_id, None)

    def get_membership(self, user_id, group_id):
        if not group_id:
            return None
        return self.memberships.get((user_id, group_id), None)

    def get_sender_role_in_group(self, sender_id, group_id):
        if not sender_id or not group_id:
            return None
        return self.sender_memberships.get(sender_id, {}).get(group_id, None)

    def get_business(self, business_id):
        if not business_id:
            return None
        return self.businesses.get(business_id, None)

    def get_user_business_rel(self, user_id, business_id):
        if not business_id:
            return None
        return self.user_business.get((user_id, business_id), None)

    def get_user_history(self, user_id):
        return self.history_by_user.get(user_id, [])

    def get_sender_history(self, user_id, sender_id):
        if not sender_id:
            return []
        return self.history_by_sender.get((user_id, sender_id), [])

    def get_business_history(self, user_id, business_id):
        if not business_id:
            return []
        return self.history_by_business.get((user_id, business_id), [])

    def get_group_history(self, user_id, group_id):
        if not group_id:
            return []
        return self.history_by_group.get((user_id, group_id), [])

    def get_event(self, message_id):
        return self.events_by_message.get(message_id, None)

    def get_avg_daily_notifications(self, user_id):
        records = self.daily_notifications.get(user_id, [])
        if not records:
            return 0, 0
        avg_sent = sum(r["sent"] for r in records) / len(records)
        avg_dismissed = sum(r["dismissed"] for r in records) / len(records)
        return avg_sent, avg_dismissed

    def is_valid_evidence_id(self, evidence_id):
        return evidence_id in self.all_history_ids
