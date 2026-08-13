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

## HTTPS להקלטה מהמיקרופון (`tailscale serve`)

הדפדפן נותן מיקרופון רק ב-HTTPS. `tailscale serve` נותן כתובת מילולית עם תעודה אמיתית (Let's Encrypt) — **רק** למכשירים ב-Tailscale.

כתובת חיה אצלנו:

`https://avichay-vostro-3560.tail7c92f6.ts.net/`

זה **לא** רץ מתיקיית הפרויקט. הגדרה חד-פעמית על המכונה (נשמרת ב-Tailscale, שורדת ריבוט). לא נוגעת ב-SSH, לא בפורט 8765, לא בשירותים אחרים.

```bash
# על שרת האודיו (יכול לדרוש sudo)
sudo tailscale serve --bg 8765
tailscale serve status
# ביטול: tailscale serve --https=443 off
```

בפעם הראשונה ב-tailnet: לאשר HTTPS בקישור ש-`serve` מדפיס. **לא** `tailscale funnel` (זה פותח לאינטרנט).

קישורי הזמנה מהממשק מצביעים לכתובת ה-HTTPS בזכות `BT_SPEAKER_PUBLIC_URL` ב-`.env`.

### איזו כתובת מתי

| כתובת | מי | מיקרופון |
|--------|-----|----------|
| `http://<LAN_IP>:8765` | רשת ביתית, מועדפים ישנים | לא |
| `http://<TAILSCALE_IP>:8765` | Tailscale, שימוש יומיומי | לא |
| `https://avichay-vostro-3560.tail7c92f6.ts.net` | Tailscale + MagicDNS | כן |

`https://<מספר-IP>` לא יעבוד — התעודה חתומה על השם המילולי בלבד.

שתי הכתובות (מספרית + מילולית) חיות במקביל. השרת לא קושר טוקן לכתובת; הדפדפן כן (origin נפרד) → כניסה ראשונה ל-HTTPS דורשת הזמנה חדשה באותו דפדפן. רישום כפול לאותו טלפון אפשרי ולא מזיק.

שאר הפיצ'רים (יוטיוב, ספרייה, פלייליסטים, העלאת קובץ קולי, בלוטות׳) עובדים גם ב-HTTP.

### DNS באנדרואיד / כרום — חשוב

השם `*.ts.net` **לא קיים ב-DNS הציבורי**. כרום עם **Private DNS** (DoH לגוגל) עוקף את MagicDNS → בדרך כלל `ERR_SSL_UNRECOGNIZED_NAME_ALERT`.

כדי שהכתובת המילולית תיפתח:

1. Tailscale בטלפון **Connected** (לא idle)
2. אנדרואיד: Private DNS **כבוי**
3. ב-Tailscale: **Use Tailscale DNS** דולק

זה **לא** חד-פעמי. כל כניסה ל-HTTPS צריכה את זה. אחרי הביקור הראשון אי אפשר להחזיר Private DNS ולכבות DNS של Tailscale — אותה שגיאה תחזור.

שימוש יומיומי מומלץ: מועדף מספרי + Private DNS דולק כמו תמיד. להקלטה מהמיקרופון: או לכבות Private DNS רק אז, או להעלות קובץ מ-Voice Memos בלי לגעת ב-DNS.

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
- **ספרייה** — העלאת קבצי אודיו, ניגון מקומי, שמירת קישור יוטיוב לדיסק
- **פלייליסטים** — יצירה, הוספת קבצים/קישורים, ניגון
- **הקלטה** — הודעה קולית מהטלפון שנשלחת לרמקול (או העלאת קובץ מ-Voice Memos)
- **אחרונים** — 50 ההאזנות האחרונות, לחיצה = ניגון מחדש

קבצי מדיה נשמרים ב־`media/` (`uploads/`, `recordings/`, `saved/`). אפשר גם לזרוק לשם קבצים ידנית מהמחשב.

הקלטה מהמיקרופון בדפדפן דורשת HTTPS — ראה סעיף `tailscale serve` למעלה. ב־HTTP אפשר תמיד להעלות קובץ קולי.

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
| `BT_SPEAKER_PUBLIC_URL` | (ריק) | בסיס לקישורי הזמנה (למשל `https://host.ts.net`) |
| `BT_SPEAKER_MEDIA_DIR` | (ריק) | תיקיית מוזיקה נוספת לסריקה (למשל `~/Music`) |

## API (עיקרי)

| Method | Path | הערה |
|--------|------|------|
| GET | `/api/health` | פתוח |
| POST | `/api/auth/redeem` | פתוח — מחליף הזמנה בטוקן מכשיר |
| POST | `/api/play` | `{ url }` או `{ file_id }` |
| POST | `/api/play/playlist` | `{ playlist_id }` |
| GET/POST | `/api/library` | רשימה / העלאה |
| POST | `/api/library/save-url` | שמירת יוטיוב לדיסק |
| POST | `/api/record` | הקלטה (multipart, `play=true` לניגון מיידי) |
| GET/POST | `/api/playlists` | פלייליסטים |
| GET | `/api/history` | האזנות אחרונות |
