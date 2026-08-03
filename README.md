# BT Speaker Remote

שליטה מרחוק (טלפון דרך **Tailscale**) ב-Bluetooth של המחשב + השמעת אודיו מיוטיוב לרמקול.

## הפעלה

```bash
systemctl --user status bt-speaker-remote.service
systemctl --user restart bt-speaker-remote.service
```

(או `start.sh` / `stop.sh` אם לא משתמשים ב-systemd)

## פתיחה מהטלפון

**קישור קבוע (בלי טוקן):** `http://<TAILSCALE_IP>:8765/`

את כתובת ה־Tailscale של השרת אפשר לקבל עם:

```bash
tailscale ip -4
```

בפעם הראשונה בכל דפדפן — צריך **קישור הזמנה חד-פעמי** (ראה למטה). אחרי זה הדפדפן זוכר לבד.

## הרשאות מכשירים (חשוב)

הדפדפן לא מזהה לבד "זה הטלפון הראשי".
**אתה** נותן שם כשיוצרים הזמנה — השם נשמר ב-JSON.

### איך זה עובד

1. `./add_device.sh "הטלפון שלי"` → קישור הזמנה ל־**24 שעות**, חד־פעמי
2. פותחים את הקישור **פעם אחת** באותו דפדפן → נרשם מכשיר ב־`authorized_devices.json`
3. הדפדפן שומר טוקן קבוע (בלי סיסמה בכל כניסה)
4. קישור ההזמנה **מת** אחרי השימוש (או אחרי 24ש) — גם אם מישהו מעביר הלאה
5. להסיר גישה: `./add_device.sh --list` ואז `--revoke dev_xxxx`

### מהממשק (מומלץ)

אם המכשיר שלך מסומן `admin` (הטלפון שלך כבר), גלול ל־**Access**:
- צור הזמנה עם שם → Copy link → שלח למכשיר
- Revoke / Delete למכשירים ישנים
- Cancel להזמנה שעדיין פתוחה

המכשיר הראשון שנרשם הופך אוטומטית ל־admin. אי אפשר למחוק את ה-admin האחרון.

### פקודות CLI (גיבוי)

```bash
./add_device.sh "הטלפון שלי"
./add_device.sh --list
./add_device.sh --revoke dev_abc123
./add_device.sh --delete dev_abc123
```

קובץ: `~/bt-speaker-remote/authorized_devices.json` (לא ב-git).

> דפדפן אחר באותו טלפון = מכשיר נפרד → צריך הזמנה חדשה.

## מה אפשר לעשות בדף

- Bluetooth on/off, Scan, Pair/Connect/Disconnect/Forget
- YouTube → Play / Pause / Resume / Stop + Volume

## תלויות

```bash
sudo apt install bluez pulseaudio-utils mpv
# yt-dlp מומלץ עדכני (pipx/apt)
```

## משתני סביבה (`.env`)

| משתנה | ברירת מחדל | משמעות |
|--------|-------------|--------|
| `BT_SPEAKER_HOST` | `0.0.0.0` | האזנה |
| `BT_SPEAKER_PORT` | `8765` | פורט |
| `BT_SPEAKER_INVITE_HOURS` | `24` | תוקף קישור הזמנה |
| `BT_SPEAKER_TOKEN` | (ריק) | אופציונלי — master bypass לחירום |

## API (עיקרי)

| Method | Path | הערה |
|--------|------|------|
| GET | `/api/health` | פתוח |
| POST | `/api/auth/redeem` | פתוח — מחליף הזמנה בטוקן מכשיר |
| GET | `/api/status` | דורש מכשיר מורשה |
| … | שאר `/api/*` | דורש מכשיר מורשה |
