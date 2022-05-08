from concurrent.futures import thread
import pynetbox
import urllib3

from ROSDevice import ROSDevice

threads = []

urllib3.disable_warnings()
nb = pynetbox.api('https://172.31.240.9/', token='7a83c6d4e4eae1cde9595cac0aa170e05919e975')
nb.http_session.verify = False

for p in nb.dcim.platforms.all():
    if(p.napalm_driver == "ros"):
        platform = p

for dev in nb.dcim.devices.filter(status="active", platform=platform.slug):
    if(dev.primary_ip4 is not None):
        thread = ROSDevice(len(threads), dev, nb)
        threads.append(thread)

for thread in threads:
    thread.start()