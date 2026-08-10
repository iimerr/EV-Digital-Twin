import json
import boto3
import uuid
import os
import tempfile
from datetime import datetime
from decimal import Decimal

s3 = boto3.client('s3', region_name='ap-southeast-2')
dynamodb = boto3.resource('dynamodb', region_name='ap-southeast-2')
twinmaker = boto3.client('iottwinmaker', region_name='ap-southeast-2')

S3_BUCKET = 'evspaces3'
MODEL_FILE = 'random_forest_params.json'
PREDICTIONS_TABLE = 'EV_Predictions'
WORKSPACE_ID = 'evtwin'
ENTITY_ID = '8d68a1e2-4b00-47f7-b65d-4f5d7771ab1c'
COMPONENT_NAME = 'VehicleData'

CORS_HEADERS = {
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': 'Content-Type',
    'Access-Control-Allow-Methods': 'POST, OPTIONS'
}

model = None

def load_model_from_s3():
    global model
    try:
        model_path = os.path.join(tempfile.gettempdir(), MODEL_FILE)
        s3.download_file(S3_BUCKET, MODEL_FILE, model_path)
        with open(model_path, 'r') as f:
            model = json.load(f)
        print(f"Model loaded: {model['n_estimators']} trees")
        return True
    except Exception as e:
        print(f"Failed to load model: {e}")
        return False

def predict_single_tree(tree, features):
    node = 0
    while tree['children_left'][node] != -1:
        feature_idx = tree['feature'][node]
        threshold = tree['threshold'][node]
        if features[feature_idx] <= threshold:
            node = tree['children_left'][node]
        else:
            node = tree['children_right'][node]
    return tree['value'][node]

def predict(features):
    predictions = [predict_single_tree(tree, features) for tree in model['trees']]
    scaled_pred = sum(predictions) / len(predictions)
    actual_pred = (scaled_pred * model['scaler_std']) + model['scaler_mean']
    return actual_pred

def update_twinmaker(car_name, predicted_range, current_range, battery_level):
    try:
        twinmaker.update_entity(
            workspaceId=WORKSPACE_ID,
            entityId=ENTITY_ID,
            componentUpdates={
                COMPONENT_NAME: {
                    'componentTypeId': 'com.ev.vehicle.data',
                    'propertyUpdates': {
                        'Car_name': {
                            'value': {
                                'stringValue': car_name
                            },
                            'updateType': 'UPDATE'
                        },
                        'Predicted_Range': {
                            'value': {
                                'doubleValue': float(predicted_range)
                            },
                            'updateType': 'UPDATE'
                        },
                        'Actual_Range': {
                            'value': {
                                'doubleValue': float(current_range)
                            },
                            'updateType': 'UPDATE'
                        },
                        'Battery_Level': {
                            'value': {
                                'doubleValue': float(battery_level)
                            },
                            'updateType': 'UPDATE'
                        }
                    }
                }
            }
        )
        print(f"TwinMaker updated for: {car_name}")
        return True
    except Exception as e:
        print(f"TwinMaker update failed: {e}")
        return False

def lambda_handler(event, context):
    global model
    print(f"Received: {json.dumps(event)}")

    # Handle CORS preflight OPTIONS request
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps('OK')
        }

    try:
        # Parse body if coming from API Gateway
        if 'body' in event:
            body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        else:
            body = event

        if model is None:
            if not load_model_from_s3():
                raise Exception("Failed to load ML model from evspaces3")

        battery = float(body.get('Battery', 75))
        efficiency = float(body.get('Efficiency', 170))
        top_speed = float(body.get('Top_speed', 180))
        car_name = body.get('Car_name', 'Unknown')

        energy_performance = battery / (efficiency + 1e-9)
        speed_ratio = top_speed / (efficiency + 1e-9)

        features = [battery, efficiency, top_speed, energy_performance, speed_ratio]

        predicted_range = predict(features)
        current_range = predicted_range * battery / 100

        print(f"Car: {car_name}")
        print(f"Predicted Range: {predicted_range:.2f} km")
        print(f"Current Range: {current_range:.2f} km")

        # Save to DynamoDB
        table = dynamodb.Table(PREDICTIONS_TABLE)
        item = {
            'id': str(uuid.uuid4()),
            'prediction_value': str(round(predicted_range, 2)),
            'timestamp': datetime.now().isoformat(),
            'Car_name': car_name,
            'Battery_Level': Decimal(str(battery)),
            'Predicted_Range': Decimal(str(round(predicted_range, 2))),
            'Current_Range': Decimal(str(round(current_range, 2)))
        }
        table.put_item(Item=item)
        print(f"Saved to DynamoDB successfully")

        # Update TwinMaker
        update_twinmaker(car_name, predicted_range, current_range, battery)

        return {
            'statusCode': 200,
            'headers': CORS_HEADERS,
            'body': json.dumps({
                'car_name': car_name,
                'predicted_range_km': round(predicted_range, 2),
                'current_range_km': round(current_range, 2),
                'battery_level': battery
            })
        }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': CORS_HEADERS,
            'body': json.dumps({'error': str(e)})
        }
