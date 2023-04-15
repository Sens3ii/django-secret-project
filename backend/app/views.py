from django.db.models import Max
from django.http import JsonResponse
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Sale, Supply
from .serializers import SaleSerializer, SupplySerializer, SaleUpdateSerializer, SupplyUpdateSerializer


def make_kwargs(barcode, from_time, to_time, is_sale):
    kwargs = {}
    if from_time:
        from_time = timezone.datetime.strptime(from_time, '%Y-%m-%d %H:%M:%S')
        kwargs['sale_time__gte' if is_sale else 'supply_time__gte'] = from_time
    if to_time:
        to_time = timezone.datetime.strptime(to_time, '%Y-%m-%d %H:%M:%S')
        kwargs['sale_time__lte' if is_sale else 'supply_time__lte'] = to_time
    if barcode:
        kwargs['barcode'] = barcode
    return kwargs


def recalculate(sales, supplies, fm, fmq):
    upd_sales = []
    supply = None
    supply_avail_q = 0
    prev_sale = None
    for sale in sales:
        matched = False
        sale.total_net_profit = prev_sale.total_net_profit if prev_sale else 0
        sale.total_quantity = prev_sale.total_quantity if prev_sale else 0
        sale.total_revenue = prev_sale.total_revenue if prev_sale else 0
        sale_q = sale.quantity
        while not matched:
            try:
                if not supply_avail_q:
                    supply = next(supplies)
                    supply_avail_q = supply.quantity
            except StopIteration:
                break
            if sale_q <= supply_avail_q:
                matched = True
            q_update = min(sale_q, supply_avail_q)
            sale_q -= q_update
            supply_avail_q -= q_update
            sale.total_net_profit += (sale.price - supply.price) * q_update
            sale.total_revenue += sale.price * q_update
            sale.total_quantity += q_update
        prev_sale = sale
        upd_sales.append(sale)
        if len(upd_sales) > 1000:
            Sale.objects.bulk_update(upd_sales, fields=[
                'total_net_profit',
                'total_net_profit',
                'total_quantity',
                'total_revenue',
            ])
            upd_sales = []
    Sale.objects.bulk_update(upd_sales, fields=[
        'total_net_profit',
        'total_net_profit',
        'total_quantity',
        'total_revenue',
    ])


def get_sales(barcode):
    all_sales = Sale.objects.filter(barcode=barcode).order_by('sale_time', 'id') \
        .iterator(chunk_size=1000)
    return all_sales


def get_supplies(barcode):
    all_supplies = Supply.objects.filter(barcode=barcode).order_by('supply_time', 'id') \
        .iterator(chunk_size=1000)
    return all_supplies


def new_supply(new_sup):
    recalculate(get_sales(new_sup.barcode), get_supplies(new_sup.barcode), None, None)



def new_sale(new_sale_):
    recalculate(get_sales(new_sale_.barcode), get_supplies(new_sale_.barcode), None, None)


class SaleViewSet(viewsets.ModelViewSet):
    queryset = Sale.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return SaleSerializer
        elif self.action == 'update':
            return SaleUpdateSerializer
        return SaleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        new_sale(serializer.instance)
        return Response(serializer.data, status=status.HTTP_200_OK, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode), None, None)
        return Response(status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode), None, None)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        barcode = request.query_params.get('barcode')
        from_time = request.query_params.get('fromTime')
        to_time = request.query_params.get('toTime')
        make_kwargs(barcode, from_time, to_time, is_sale=True)
        queryset = self.filter_queryset(self.get_queryset()).filter(**kwargs)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class SupplyViewSet(viewsets.ModelViewSet):
    queryset = Supply.objects.all()

    def get_serializer_class(self):
        if self.action == 'create':
            return SupplySerializer
        elif self.action == 'update':
            return SupplyUpdateSerializer
        return SupplySerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        new_supply(serializer.instance)
        return Response(serializer.data, status=status.HTTP_200_OK, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode), None, None)
        return Response(status=status.HTTP_200_OK)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode), None, None)

        return Response(serializer.data, status=status.HTTP_200_OK)

    def list(self, request, *args, **kwargs):
        barcode = request.query_params.get('barcode')
        from_time = request.query_params.get('fromTime')
        to_time = request.query_params.get('toTime')
        make_kwargs(barcode, from_time, to_time, is_sale=False)
        queryset = self.filter_queryset(self.get_queryset()).filter(**kwargs)

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


@api_view(['GET'])
def get_reports(request):
    barcode = request.query_params.get('barcode')
    from_time = request.query_params.get('fromTime')
    to_time = request.query_params.get('toTime')

    if not barcode or not from_time or not to_time:
        return JsonResponse({'error': 'Missing required parameters'}, status=400)

    try:
        from_time = timezone.datetime.strptime(from_time, '%Y-%m-%d %H:%M:%S')
        to_time = timezone.datetime.strptime(to_time, '%Y-%m-%d %H:%M:%S')
        barcode = int(barcode)
    except ValueError:
        return JsonResponse({'error': 'Invalid datetime format'}, status=400)

    gt = lt = None

    gt_time = Sale.objects.filter(barcode=barcode, sale_time__lte=to_time).aggregate(Max('sale_time'))['sale_time__max']
    lt_time = Sale.objects.filter(barcode=barcode, sale_time__lt=from_time).aggregate(Max('sale_time'))['sale_time__max']

    if gt_time:
        gt_id = Sale.objects.filter(barcode=barcode, sale_time=gt_time).aggregate(Max('id'))['id__max']
        gt = Sale.objects.get(id=gt_id)
    if lt_time:
        lt_id = Sale.objects.filter(barcode=barcode, sale_time=lt_time).aggregate(Max('id'))['id__max']
        lt = Sale.objects.get(id=lt_id)

    rev = prof = quantity = 0
    if gt:
        rev += gt.total_revenue
        prof += gt.total_net_profit
        quantity += gt.total_quantity
    if lt:
        rev -= lt.total_revenue
        prof -= lt.total_net_profit
        quantity -= lt.total_quantity

    return JsonResponse({
        'barcode': barcode,
        'revenue': rev,
        'netProfit': prof,
        'quantity': quantity,
    }, status=200)
