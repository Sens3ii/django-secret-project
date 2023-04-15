from django.db import models


class Sale(models.Model):
    id = models.AutoField(primary_key=True)
    barcode = models.BigIntegerField()
    quantity = models.IntegerField(default=1)
    price = models.IntegerField(default=0)
    sale_time = models.DateTimeField()
    total_net_profit = models.BigIntegerField(default=0)
    total_revenue = models.BigIntegerField(default=0)
    total_quantity = models.BigIntegerField(default=0)
    first_matched_supply = models.ForeignKey('Supply', on_delete=models.DO_NOTHING, null=True, related_name='xx')
    fms_available_quantity = models.IntegerField(null=True)
    last_matched_supply = models.ForeignKey('Supply', on_delete=models.DO_NOTHING, null=True, related_name='yy')
    lms_remaining_quantity = models.IntegerField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=['barcode', 'sale_time', 'id']),
        ]
        db_table = 'umag_hacknu_sale'


class Supply(models.Model):
    id = models.AutoField(primary_key=True)
    barcode = models.BigIntegerField()
    quantity = models.IntegerField(default=1)
    price = models.IntegerField(default=0)
    supply_time = models.DateTimeField()
    first_matched_sale_id = models.IntegerField(null=True)

    class Meta:
        indexes = [
            models.Index(fields=['barcode', 'supply_time', 'id']),
        ]
        db_table = 'umag_hacknu_supply'


