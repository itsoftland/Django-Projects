from django.shortcuts import render
from .models import Order,Vendor,Device, PushSubscription
from rest_framework.decorators import api_view,permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .serializers import OrdersSerializer 
from rest_framework import status
from django.core.cache import cache
from django.utils import timezone
import pytz

def get_current_ist_time():
    ist = pytz.timezone('Asia/Kolkata')
    return timezone.now().astimezone(ist)  # Convert UTC to IST

@api_view(['GET'])
@permission_classes([AllowAny])
def get_current_time(request):
    current_time = get_current_ist_time()
    return Response({'current_time': current_time.strftime('%Y-%m-%d %H:%M:%S')})



def manage_order(request):
    cache.clear()
    return render(request, 'order_management.html')


@api_view(['GET'])
@permission_classes([AllowAny])
def list_order(request):
    orders = Order.objects.all()  
    serializer = OrdersSerializer(orders, many=True)
    return Response(serializer.data)
   
# @api_view(['PATCH'])
# @permission_classes([AllowAny])
# def update_order(request):
#     """
#     This endpoint is used for updating an existing order's token status to "ready".
#     If the order (token) does not exist, it creates a new order with status "ready".
#     Additionally, if the current status is "ready" and the request specifies "delete",
#     the order is deleted.
#     """
#     try:
#         data = request.data
#         vendor_id = data.get('vendor_id')
#         device_id = data.get('device_id')
#         counter_no = data.get('counter_no')
#         token_no = data.get('token_no')
#         status_to_update = data.get('status')

#         if not token_no or not status_to_update or not vendor_id or not device_id or not counter_no:
#             return Response(
#                 {"message": "Token number and status are required."},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#         vendors = Vendor.objects.get(vendor_id=vendor_id)  # Fetch the vendor instance
#         devices = Device.objects.get(serial_no=device_id)
#         try:
#             # Try to fetch the existing order
#             order = Order.objects.get(token_no=token_no, vendor=vendors.id)
#             # Otherwise, update the order's status to the provided status (typically "ready")
#             order.status = status_to_update
#             order.counter_no = counter_no
#             order.save()
#             return Response(
#                 {"message": "Order status updated.", "token_no": token_no, "status": order.status},
#                 status=status.HTTP_200_OK
#             )

#         except Order.DoesNotExist:
#             # Order doesn't exist; create a new order with the status "ready"
#             # Here, we assume that if an order is created via update_order, its status must be "ready"
#             # If the client passes a different status, you can decide how to handle it.
#             new_order_data = {
#                 'token_no': token_no,
#                 'vendor': vendors.id,
#                 'device_id':devices.id,
#                 'counter_no':counter_no,
#                 'status': "ready"
#             }
#             serializer = OrdersSerializer(data=new_order_data)
#             if serializer.is_valid():
#                 serializer.save()
#                 return Response(
#                     {"message": "Order status updated.", "token_no": token_no, "status": "ready"},
#                     status=status.HTTP_201_CREATED
#                 )
#             return Response(
#                 {"message": serializer.errors},
#                 status=status.HTTP_400_BAD_REQUEST
#             )

#     except Exception as e:
#         return Response(
#             {"message": str(e)},
#             status=status.HTTP_500_INTERNAL_SERVER_ERROR
#         )

from .utils import send_push_notification

@api_view(['PATCH'])
@permission_classes([AllowAny])
def update_order(request):
    """
    This endpoint updates an existing order's token status to "ready".
    If the order (token) does not exist, it creates a new order with status "ready".
    After updating the order, it sends a push notification to the subscriptions
    associated with that order.
    """
    try:
        data = request.data
        vendor_id = data.get('vendor_id')
        device_id = data.get('device_id')
        counter_no = data.get('counter_no')
        token_no = data.get('token_no')
        status_to_update = data.get('status')

        if not token_no or not status_to_update or not vendor_id or not device_id or not counter_no:
            return Response(
                {"message": "Token number, status, vendor_id, device_id, and counter_no are required."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch the vendor and device instances
        vendor = Vendor.objects.get(vendor_id=vendor_id)
        device = Device.objects.get(serial_no=device_id)

        try:
            # Try to fetch the existing order
            order = Order.objects.get(token_no=token_no, vendor=vendor.id)
            # Update the order's status and counter number
            order.status = status_to_update
            order.counter_no = counter_no
            order.save()

        except Order.DoesNotExist:
            # Order doesn't exist; create a new order with status "ready"
            new_order_data = {
                'token_no': token_no,
                'vendor': vendor.id,
                'device_id': device.id,
                'counter_no': counter_no,
                'status': "ready"
            }
            serializer = OrdersSerializer(data=new_order_data)
            if serializer.is_valid():
                serializer.save()
            else:
                return Response(
                    {"message": serializer.errors},
                    status=status.HTTP_400_BAD_REQUEST
                )

        # After updating/creating the order, send push notifications
        subscriptions = PushSubscription.objects.filter(tokens__token_no=token_no)
        # payload = "Your order is ready!" 
        payload = {
            "title": "Order Update",
            "body": f"Your order {token_no} is now ready.",
            "token_no": token_no,
            "status": status_to_update,
            "counter_no": counter_no
        }
        push_errors = []

        for subscription in subscriptions:
            subscription_info = {
                "endpoint": subscription.endpoint,
                "keys": {
                    "p256dh": subscription.p256dh,
                    "auth": subscription.auth
                }
            }
            try:
                send_push_notification(subscription_info, payload)
            except Exception as e:
                push_errors.append(str(e))

        # Decide the response based on whether push notifications succeeded.
        if push_errors:
            return Response(
                {
                    "message": "Order updated, but push notifications encountered errors.",
                    "push_errors": push_errors
                },
                status=status.HTTP_207_MULTI_STATUS
            )
        else:
            return Response(
                {"message": "Order updated and notifications sent.", "token_no": token_no},
                status=status.HTTP_200_OK
            )

    except Exception as e:
        return Response(
            {"message": str(e)},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )



# views.py
import requests
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

@csrf_exempt  # Disable CSRF if you don't have a token from the device
def proxy_update_order(request):
    """
    This view acts as a proxy for the update_order endpoint.
    It accepts an HTTP request from the ESP8266 and forwards it to the HTTPS API.
    """
    # Adjust this URL to match your HTTPS endpoint (including the '/api/update-order/' path)
    target_url = "https://feline-clever-mutually.ngrok-free.app/vendors/api/update-order/"
    
    # Copy request headers. Remove 'Host' header so that 'requests' can set it automatically.
    headers = {key: value for key, value in request.headers.items() if key.lower() != "host"}

    try:
        # Forward PATCH requests (your update_order endpoint uses PATCH)
        if request.method.upper() == "PATCH":
            response = requests.patch(
                target_url,
                data=request.body,  # Passing raw body data
                headers=headers,
                timeout=10  # Adjust timeout as needed
            )
        # For any other method, you might want to support GET (or add more conditions)
        else:
            response = requests.get(
                target_url,
                params=request.GET,
                headers=headers,
                timeout=10
            )

        # Return the proxied response content and status code back to the caller
        django_response = HttpResponse(
            response.content,
            status=response.status_code,
            content_type=response.headers.get("Content-Type", "application/octet-stream")
        )
        return django_response

    except requests.RequestException as e:
        # In case of error, return a 500 response with an error message
        error_message = f"Error proxying request: {str(e)}"
        return HttpResponse(error_message, status=500)

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
import json

@api_view(['POST'])
@permission_classes([AllowAny])
def save_subscription(request):
    data = json.loads(request.body)
    endpoint = data.get("endpoint")
    keys = data.get("keys", {})
    browser_id = data.get("browser_id")
    token_number = data.get("token_number")

    if not endpoint or not browser_id or not token_number:
        return Response({"error": "Invalid subscription data"}, status=400)

    # Get or create subscription by browser_id
    subscription, created = PushSubscription.objects.get_or_create(
        browser_id=browser_id,
        defaults={
            "endpoint": endpoint,
            "p256dh": keys.get("p256dh", ""),
            "auth": keys.get("auth", ""),
        },
    )

    # Update keys in case they changed
    subscription.endpoint = endpoint
    subscription.p256dh = keys.get("p256dh", "")
    subscription.auth = keys.get("auth", "")
    subscription.save()

    # Link the subscription to the token
    order = get_object_or_404(Order, token_no=token_number)
    subscription.tokens.add(order)  # Add token to subscription

    return Response({"message": "Subscription updated successfully"})
