import json
import time
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient

# Configuration for the MQTT client
client = AWSIoTMQTTClient("EV Car Publisher")
client.configureEndpoint("a3he4npuz3cbzz-ats.iot.ap-southeast-2.amazonaws.com", 8883)
client.configureCredentials(
    r"C:\Users\Harith\Downloads\DT\AmazonRootCA1.pem",
    r"C:\Users\Harith\Downloads\DT\0bfbcf5e0fccc23ff53c44b1525e9c33920525c8f14483dec4aec90e12dc3ae9-private.pem.key",
    r"C:\Users\Harith\Downloads\DT\0bfbcf5e0fccc23ff53c44b1525e9c33920525c8f14483dec4aec90e12dc3ae9-certificate.pem.crt"
)

# Additional configurations
client.configureOfflinePublishQueueing(-1)
client.configureDrainingFrequency(2)
client.configureConnectDisconnectTimeout(10)
client.configureMQTTOperationTimeout(5)

def connect_client():
    try:
        client.connect()
        print("Connected to AWS IoT Core in Sydney (ap-southeast-2)")
        return True
    except Exception as e:
        print(f"Failed to connect: {e}")
        return False

# Connect
if not connect_client():
    exit(1)

# Open and read the JSON file
try:
    with open(r"C:\Users\Harith\Downloads\DT\csvjson.json", 'r') as json_file:
        car_data = json.load(json_file)

    for i, record in enumerate(car_data):
        message = {k: record[k] for k in record.keys()}

        # Try to publish, reconnect once if it fails
        try:
            client.publish("ev/car/data", json.dumps(message), 0)
            print(f"Published record {i+1}: {message}")
        except Exception as e:
            print(f"Publish failed: {e}. Reconnecting...")
            time.sleep(2)
            if connect_client():
                try:
                    client.publish("ev/car/data", json.dumps(message), 0)
                    print(f"Published record {i+1} after reconnect: {message}")
                except Exception as e2:
                    print(f"Failed again on record {i+1}: {e2}")

        time.sleep(2)  # Delay between publishing messages

except FileNotFoundError:
    print("The file 'csvjson.json' was not found.")
except json.JSONDecodeError as e:
    print(f"Error decoding JSON: {e}")

# Disconnect safely
try:
    client.disconnect()
    print("Disconnected from AWS IoT Core")
except Exception:
    print("All records published. Done!")
