from django.shortcuts import render
from rest_framework.mixins import CreateModelMixin, RetrieveModelMixin, DestroyModelMixin
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from order.serializers import CartSerializer, CartItemSerializer,AddCartItemSerializer,UpdateCartItemSerializer
from order.models import Cart, CartItem,Order,OrderItem
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from order import serializers as orderSz
from rest_framework.decorators import action
from order.services import OrderService
from rest_framework.response import Response
from rest_framework import status
from rest_framework.decorators import api_view
from sslcommerz_lib import SSLCOMMERZ
from django.conf import settings as mainsettings
from django.http import HttpResponseRedirect
# Create your views here.

class CartViewSet(CreateModelMixin, RetrieveModelMixin, DestroyModelMixin, GenericViewSet):
    serializer_class = CartSerializer
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
        
    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Cart.objects.none()
        return Cart.objects.prefetch_related('items__product').filter(user=self.request.user)
    
    def create(self, request, *args, **kwargs):
        existing_Cart=Cart.objects.filter(user=self.request.user).first()
        if existing_Cart:
            serializer=self.get_serializer(existing_Cart)
            return Response(serializer.data, status=status.HTTP_200_OK)
        return super().create(request,*args,**kwargs)
        
class CartItemViewSet(ModelViewSet):
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return AddCartItemSerializer
        elif self.request.method == 'PATCH':
            return UpdateCartItemSerializer
        return CartItemSerializer
    
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        if getattr(self, 'swagger_fake_view', False):
            return context

        return {'cart_id': self.kwargs.get('cart_pk')}
    
    def get_queryset(self):
        return CartItem.objects.select_related('product').filter(cart_id=self.kwargs.get('cart_pk'))
    
class OrderViewset(ModelViewSet):
    http_method_names = ['get', 'post', 'delete', 'patch', 'head', 'options']

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        order = self.get_object()
        OrderService.cancel_order(order=order, user=request.user)
        return Response({'status': 'Order canceled'})

    @action(detail=True, methods=['patch'])
    def update_status(self, request, pk=None):
        order = self.get_object()
        serializer = orderSz.UpdateOrderSerializer(
            order, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({'status': f'Order status updated to {request.data['status']}'})

    def get_permissions(self):
        if self.action in ['update_status', 'destroy']:
            return [IsAdminUser()]
        return [IsAuthenticated()]

    def get_serializer_class(self):
        if self.action == 'cancel':
            return orderSz.EmptySerializer
        if self.action == 'create':
            return orderSz.CreateOrderSerializer
        elif self.action == 'update_status':
            return orderSz.UpdateOrderSerializer
        return orderSz.OrderSerializer

    def get_serializer_context(self):
        if getattr(self, 'swagger_fake_view', False):
            return super().get_serializer_context()
        return {'user_id': self.request.user.id, 'user': self.request.user}

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()
        if self.request.user.is_staff:
            return Order.objects.prefetch_related('items__product').all()
        return Order.objects.prefetch_related('items__product').filter(user=self.request.user)

@api_view(['POST'])
def initiate_payment(request):
    user=request.user
    amount=request.data.get("amount")
    order_id=request.data.get("orderId")
    num_items=request.data.get("numItems")

    settings = { 'store_id':'phima68e538afdcefc', 'store_pass': 'phima68e538afdcefc@ssl', 'issandbox': True }
    sslcz = SSLCOMMERZ(settings)
    post_body = {}
    post_body['total_amount'] = amount
    post_body['currency'] = "BDT"
    post_body['tran_id'] = f"txn_{order_id}"
    post_body['success_url'] = f"{mainsettings.BACKEND_URL}/api/v1/payment/success/"
    post_body['fail_url'] = f"{mainsettings.BACKEND_URL}/api/v1/payment/fail/"
    post_body['cancel_url'] = f"{mainsettings.BACKEND_URL}/api/v1/payment/cancel/"
    post_body['emi_option'] = 0
    post_body['cus_name'] = f'{user.first_name} {user.last_name}'
    post_body['cus_email'] = user.email
    post_body['cus_phone'] = user.phone_number
    post_body['cus_add1'] = user.address
    post_body['cus_city'] = "Chittagong"
    post_body['cus_country'] = "Bangladesh"
    post_body['shipping_method'] = "NO"
    post_body['multi_card_name'] = ""
    post_body['num_of_item'] = num_items
    post_body['product_name'] = "E-commerce Products"
    post_body['product_category'] = "General"
    post_body['product_profile'] = "general"


    response = sslcz.createSession(post_body) # API response
    # print(response)

    if response.get("status")=='SUCCESS':
        return Response({"payment_url":response['GatewayPageURL']})
    return Response({'error':'Payment initiation '},status=status.HTTP_400_BAD_REQUEST)

@api_view(['POST'])
def payment_success(request):
    order_id=request.data.get("tran_id").split('_')[1]
    order=Order.objects.get(id=order_id)
    order.status="Ready To Ship"
    order.save()
    return HttpResponseRedirect(f"{mainsettings.FRONTEND_URL}/dashboard/payment/order/")

@api_view(['POST'])
def payment_cancel(request):
    return HttpResponseRedirect(f"{mainsettings.FRONTEND_URL}/dashboard/payment/order/")

@api_view(['POST'])
def payment_fail(request):
    return HttpResponseRedirect(f"{mainsettings.FRONTEND_URL}/dashboard/payment/order/")
