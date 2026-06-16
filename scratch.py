from vinylsplit.fingerprint import Fingerprinter

fingerprinter = Fingerprinter()

fp = fingerprinter.fingerprint(
    "/home/jaypee/Desktop/music/raw FLAC/born to kill.flac"
)

print(fp.duration)
print(fp.fingerprint[:80] + "...")