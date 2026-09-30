# Antex Superset Portal

Antex uchun Superset boshqaruv portalining boshlang'ich versiyasi.

## Imkoniyatlar

- Antex logotipi bilan animatsiyali bosh sahifa
- Sessiya asosidagi admin autentifikatsiyasi
- Foydalanuvchilarni yaratish, tahrirlash, faollashtirish va o'chirish
- Admin, muharrir va kuzatuvchi rollari
- Superset REST API orqali datasetlarni nomini o'zgartirmasdan sinxronlash
- Dataset qidiruvi, schema va manba bazasi ma'lumotlari

## Ishga tushirish

```bash
cp .env.example .env
docker compose up -d --build
```

Ilova standart holatda `127.0.0.1:8108` manziliga bog'lanadi.
