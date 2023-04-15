from django.views.decorators.csrf import csrf_exempt
from rest_framework import viewsets, status
from rest_framework.response import Response
from itertools import chain

from .serializers import SaleSerializer, SupplySerializer, SaleUpdateSerializer, SupplyUpdateSerializer
from django.db.models import Sum, Min, Max, Q
from django.http import JsonResponse
from django.utils import timezone
from rest_framework.decorators import api_view
from .models import Sale, Supply
from rest_framework import generics, mixins, views


def recalculate(sales, supplies, prev_sale, fm, fmq):
    upd_sales = []
    supply_avail_q = None
    for sale in sales:
        upd_supplies = []
        matched = False
        first_supply_matched = False
        sale.total_net_profit = prev_sale.total_net_profit if prev_sale else 0
        sale.total_quantity = prev_sale.total_quantity if prev_sale else 0
        sale.total_revenue = prev_sale.total_revenue if prev_sale else 0
        sale_q = sale.quantity
        while not matched:
            try:
                if not supply_avail_q:
                    supply = next(supplies)
                    if supply_avail_q == 0:
                        supply.first_matched_sale_id = None
            except StopIteration:
                break
            supply_avail_q = supply.quantity if supply.id != fm else fmq
            if sale_q <= supply_avail_q:
                matched = True
            q_update = min(sale_q, supply_avail_q)
            sale_q -= q_update
            if not first_supply_matched:
                first_supply_matched = True
                sale.first_matched_supply = supply
                sale.fms_available_quantity = supply_avail_q
            supply_avail_q -= q_update
            if supply.first_matched_sale_id is None:
                supply.first_matched_sale_id = sale.id  # TODO: check
            if sale_q == 0:
                sale.last_matched_supply = supply
                sale.lms_remaining_quantity = supply_avail_q
            sale.total_net_profit += sale.price * q_update
            sale.total_revenue += (sale.price - supply.price) * q_update
            sale.total_quantity += q_update
            upd_supplies.append(supply)
            if len(upd_supplies) > 1000:
                Supply.objects.bulk_update(upd_supplies, fields=['first_matched_sale_id'])
                upd_supplies = []
        Supply.objects.bulk_update(upd_supplies, fields=['first_matched_sale_id'])
        prev_sale = sale
        upd_sales.append(sale)
        if len(upd_sales) > 1000:
            Sale.objects.bulk_update(upd_sales, fields=[
                'total_net_profit',
                'total_net_profit',
                'total_quantity',
                'total_revenue',
                'first_matched_supply',
                'fms_available_quantity',
                'last_matched_supply',
                'lms_remaining_quantity',
            ])
            upd_sales = []
        fm = supply.id
        fmq = ...
    Sale.objects.bulk_update(upd_sales, fields=[
        'total_net_profit',
        'total_net_profit',
        'total_quantity',
        'total_revenue',
        'first_matched_supply',
        'fms_available_quantity',
        'last_matched_supply',
        'lms_remaining_quantity',
    ])


def get_sales(barcode, dt_from=None):
    kwargs = dict(barcode=barcode)
    if dt_from:
        kwargs['sale_time__gte'] = dt_from
    all_sales = Sale.objects.filter(**kwargs).order_by('sale_time', 'id') \
        .iterator(chunk_size=1000)
    return all_sales


def get_supplies(barcode, dt_from=None, id_from=None):
    kwargs = dict(barcode=barcode)
    args = []
    if dt_from:
        kwargs['supply_time__gte'] = dt_from
    if id_from:
        kwargs = {}
        args = [Q(supply_time__gte=dt_from) | Q(supply_time=dt_from, id__gte=id_from)]
    all_supplies = Supply.objects.filter(*args, **kwargs).order_by('supply_time', 'id') \
        .iterator(chunk_size=1000)
    # msg = ''
    # for sup in all_supplies:
    #     msg += f'{sup.supply_time} '
    # assert 0, msg
    return all_supplies


def new_supply(new_sup):
    sales = get_sales(new_sup.barcode, dt_from=new_sup.supply_time)
    try:
        sale = next(sales)
    except StopIteration:
        return
    prev_sale = Sale.objects.filter(Q(sale_time__lt=sale.sale_time) | Q(sale_time=sale.sale_time, id__lt=sale.id)) \
        .order_by('sale_time').last()
    prev_supply = Supply.objects.filter(Q(supply_time__lt=new_sup.supply_time) | Q(supply_time=new_sup.supply_time, id__lt=new_sup.id)) \
        .order_by('supply_time').last()
    fm = fmq = None

    if prev_supply is None:
        supplies = get_supplies(new_sup.barcode)
    else:
        if new_sup.supply_time > sale.first_matched_supply and sale.first_matched_supply.supply_time:
            supplies = get_supplies(new_sup.barcode, dt_from=sale.first_matched_supply.supply_time, id_from=sale.first_matched_supply.id)
            fm = sale.first_matched_supply.id
            fmq = sale.fms_available_quantity
        else:
            supplies = get_supplies(new_sup.barcode)
    recalculate(chain([sale], sales), supplies, prev_sale, fm, fmq)



def new_sale(new_sale_):
    sales = get_sales(new_sale_.barcode, dt_from=new_sale_.sale_time)
    try:
        sale = next(sales)
    except StopIteration:
        return
    prev_sale = Sale.objects.filter(Q(sale_time__lt=sale.sale_time) | Q(sale_time=sale.sale_time, id__lt=sale.id)) \
        .order_by('sale_time').last()
    if prev_sale is None:
        supplies = get_supplies(new_sale_.barcode)
    else:
        if prev_sale.last_matched_supply is None:
            return
        supplies = get_supplies(new_sale_.barcode,
                                id_from=prev_sale.last_matched_supply.id,
                                dt_from=prev_sale.last_matched_supply.supply_time)
    recalculate(chain([sale], sales), supplies, prev_sale,
                prev_sale.last_matched_supply.id if prev_sale and prev_sale.last_matched_supply else None,
                prev_sale.lms_remaining_quantity if prev_sale and prev_sale.last_matched_supply else None)


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
    except ValueError:
        return JsonResponse({'error': 'Invalid datetime format'}, status=400)

    # sales = Sale.objects.filter(barcode=barcode, sale_time__gte=from_time, sale_time__lte=to_time)
    #
    # quantity = sales.aggregate(Sum('quantity'))['quantity__sum'] or 0
    # revenue = sales.aggregate(Sum('price'))['price__sum'] or 0
    # net_profit = sales.aggregate(Sum('price') - Sum('supply__price'))['price__sum'] or 0
    #
    # response_data = {
    #     'barcode': barcode,
    #     'quantity': quantity,
    #     'revenue': revenue,
    #     'netProfit': net_profit
    # }

    return JsonResponse({'good': 'good'}, status=200)
