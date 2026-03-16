# -*- coding: utf-8 -*-
from odoo import models, fields

class CrmStage(models.Model):
    _inherit = 'crm.stage'

    active = fields.Boolean(default=True)