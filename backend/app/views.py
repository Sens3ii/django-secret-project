from django.db.models import Max, Q
from django.http import JsonResponse
from django.utils import timezone

from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from .models import Sale, Supply
from .serializers import SaleSerializer, SupplySerializer, SaleUpdateSerializer, SupplyUpdateSerializer

UPDATE_DESTROY_STATUS = status.HTTP_200_OK


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


def recalculate(sales, supplies, supply_avail_q=0, prev_sale=None):
    upd_sales = []
    supply = None
    for sale in sales:
        matched = False
        sale.total_net_profit = prev_sale.total_net_profit if prev_sale else 0
        sale.total_quantity = prev_sale.total_quantity if prev_sale else 0
        sale.total_revenue = prev_sale.total_revenue if prev_sale else 0
        sale_q = sale.quantity
        while not matched:
            try:
                if supply is None and supply_avail_q:
                    supply = next(supplies)
                if not supply_avail_q:
                    supply = next(supplies)
                    supply_avail_q = supply.quantity
            except StopIteration:
                break
            q_update = min(sale_q, supply_avail_q)
            if sale_q <= supply_avail_q:
                matched = True
                sale.last_connected_supply = supply
                sale.last_connected_supply_remaining_q = supply_avail_q - q_update
            sale_q -= q_update
            supply_avail_q -= q_update
            sale.total_net_profit += (sale.price - supply.price) * q_update
            sale.total_revenue += sale.price * q_update
            sale.total_quantity += q_update
        if not matched:
            sale.total_revenue += sale.price * sale_q
            sale.total_net_profit += sale.price * sale_q
            sale.total_quantity += sale_q
        if prev_sale:
            prev_sale.last_connected_supply = None
            prev_sale.last_connected_supply_remaining_q = None
        prev_sale = sale
        upd_sales.append(sale)
        if len(upd_sales) > 1000:
            Sale.objects.bulk_update(upd_sales, fields=[
                'total_net_profit',
                'total_quantity',
                'total_revenue',
                'last_connected_supply',
                'last_connected_supply_remaining_q'
            ])
            upd_sales = []
    Sale.objects.bulk_update(upd_sales, fields=[
        'total_net_profit',
        'total_quantity',
        'total_revenue',
        'last_connected_supply',
        'last_connected_supply_remaining_q'
    ])


def get_sales(barcode):
    all_sales = Sale.objects.filter(barcode=barcode).order_by('sale_time', 'id') \
        .iterator(chunk_size=1000)
    return all_sales


def get_supplies(barcode, first_supply=None):
    if first_supply:
        return Supply.objects.filter(
            Q(supply_time__gt=first_supply.supply_time) | Q(supply_time=first_supply.supply_time, id__gte=first_supply.id),
            barcode=barcode
        ).order_by('supply_time', 'id').iterator(chunk_size=1000)
    all_supplies = Supply.objects.filter(barcode=barcode).order_by('supply_time', 'id') \
        .iterator(chunk_size=1000)
    return all_supplies


def new_supply(new_sup):
    recalculate(get_sales(new_sup.barcode), get_supplies(new_sup.barcode))



def new_sale(new_sale_):
    recalculate(get_sales(new_sale_.barcode), get_supplies(new_sale_.barcode))


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
        max_sale_time = Sale.objects.filter(barcode=serializer.validated_data['barcode']).aggregate(Max('sale_time'))['sale_time__max']
        self.perform_create(serializer)
        if max_sale_time is not None and max_sale_time <= serializer.instance.sale_time:
            sale = Sale.objects.get(id=Sale.objects.filter(sale_time=max_sale_time).aggregate(Max('id'))['id__max'])
            if sale.last_connected_supply:   
                supplies = get_supplies(serializer.instance.barcode, sale.last_connected_supply)
                recalculate([serializer.instance], supplies, sale.last_connected_supply_remaining_q, sale)
            else:
                recalculate([serializer.instance], iter(()), prev_sale=sale)
        else:
            new_sale(serializer.instance)
        headers = self.get_success_headers(serializer.data)
        return JsonResponse({'id': serializer.instance.id}, status=status.HTTP_200_OK, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode))
        return Response(status=UPDATE_DESTROY_STATUS)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode))

        return Response(status=UPDATE_DESTROY_STATUS)

    def list(self, request, *args, **kwargs):
        barcode = request.query_params.get('barcode')
        from_time = request.query_params.get('fromTime')
        to_time = request.query_params.get('toTime')
        queryset = self.filter_queryset(self.get_queryset()).filter(**make_kwargs(barcode, from_time, to_time, is_sale=True))

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
        max_sale_time = Sale.objects.filter(barcode=serializer.instance.barcode).aggregate(Max('sale_time'))['sale_time__max']
        if max_sale_time is not None and max_sale_time < serializer.instance.supply_time:
            pass
        else:
            new_supply(serializer.instance)
        headers = self.get_success_headers(serializer.data)
        return JsonResponse({'id': serializer.instance.id}, status=status.HTTP_200_OK, headers=headers)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self.perform_destroy(instance)
        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode))
        return Response(status=UPDATE_DESTROY_STATUS)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)

        if getattr(instance, '_prefetched_objects_cache', None):
            instance._prefetched_objects_cache = {}

        recalculate(get_sales(instance.barcode), get_supplies(instance.barcode))

        return Response(status=UPDATE_DESTROY_STATUS)

    def list(self, request, *args, **kwargs):
        barcode = request.query_params.get('barcode')
        from_time = request.query_params.get('fromTime')
        to_time = request.query_params.get('toTime')
        queryset = self.filter_queryset(self.get_queryset()).filter(**make_kwargs(barcode, from_time, to_time, is_sale=False))

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
