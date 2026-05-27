import qrcode

link = "http://127.0.0.1:5000"

img = qrcode.make(link)

img.save("qrcode.png")

print("QR Code ساخته شد")