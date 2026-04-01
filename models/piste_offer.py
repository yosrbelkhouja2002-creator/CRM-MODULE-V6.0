# -*- coding: utf-8 -*-
from odoo import models, fields, api

class PisteOffer(models.Model):
    _name = 'piste.offer'
    _description = 'Projet commercial trouvé'
    _rec_name = 'name'
    _order = 'scraped_date desc'
    
    # ===== CHAMPS DE BASE =====
    name = fields.Char(string='Titre du projet')  
    
    # RELATION AVEC LA SOURCE
    source_id = fields.Many2one(
        'piste.source',
        string='Source',
        ondelete='cascade'
    )
    
    # INFORMATIONS DU PROJET
    url = fields.Char(string='URL')
    description = fields.Html(string='Description')
    website = fields.Char(string='Plateforme')
    budget = fields.Char(string='Budget')
    
    # ===== CHAMPS CLIENT/CONTACT - MODIFIÉ =====
    # SUPPRIMÉ : partner_id (Many2one) → remplacé par partner_name (Char)
    # SUPPRIMÉ : person_partner_id (plus de contact séparé)
    
    partner_name = fields.Char(
        string='Nom de la société',
        help='Nom de l\'entreprise cliente (sera créée en tant que partner à la conversion)'
    )
    
    email_from = fields.Char(string='Email')
    phone = fields.Char(string='Téléphone')
    
    Mode_de_livraison = fields.Selection([
        ('regie', 'Régie'),
        ('forfait', 'Forfait'),
        ('mixte', 'Mixte'),
    ], string='Mode de livraison')
    
    # ===== BUSINESS UNIT / OFFRE / SOUS-OFFRE - CORRIGÉ =====
    business_unit_id = fields.Many2one(
        'hr.business.unit',  # ✅ CORRIGÉ : 'business.unit' → 'hr.business.unit'
        string='Business unit',
        help='Unité commerciale responsable'
    )
    
    # ✅ NOUVEAU : Offre et sous-offre (comme dans crm.lead et piste.source)
    offre_id = fields.Many2one(
        'business.unit.offre',
        string='Offre',
        domain="[('business_unit_id', '=', business_unit_id)]"
    )
    
    sub_offre_id = fields.Many2one(
        'business.unit.suboffre',
        string='Sous-offre',
        domain="[('offre_id', '=', offre_id)]"
    )
    
    # ===== CHAMPS CALCULÉS POUR DOMAINE DYNAMIQUE =====
    offre_domain = fields.Char(
        compute='_compute_offre_domain',
        store=False
    )
    
    sub_offre_domain = fields.Char(
        compute='_compute_sub_offre_domain',
        store=False
    )
    
    @api.depends('business_unit_id')
    def _compute_offre_domain(self):
        for rec in self:
            if rec.business_unit_id:
                offre_ids = rec.business_unit_id.offre_ids.ids
                rec.offre_domain = [('id', 'in', offre_ids)]
            else:
                rec.offre_domain = []
    
    @api.depends('business_unit_id', 'offre_id')
    def _compute_sub_offre_domain(self):
        for rec in self:
            if rec.offre_id:
                rec.sub_offre_domain = [('offre_id', '=', rec.offre_id.id)]
            elif rec.business_unit_id:
                offre_ids = rec.business_unit_id.offre_ids.ids
                rec.sub_offre_domain = [('offre_id', 'in', offre_ids)]
            else:
                rec.sub_offre_domain = []
    
    # ===== ONCHANGES POUR CASCADING =====
    @api.onchange('business_unit_id')
    def _onchange_business_unit_id(self):
        if self.business_unit_id:
            if self.offre_id and self.offre_id.business_unit_id != self.business_unit_id:
                self.offre_id = False
                self.sub_offre_id = False
        else:
            self.offre_id = False
            self.sub_offre_id = False
    
    @api.onchange('offre_id')
    def _onchange_offre_id(self):
        if self.offre_id:
            if not self.business_unit_id:
                self.business_unit_id = self.offre_id.business_unit_id.id
            if self.sub_offre_id and self.sub_offre_id.offre_id != self.offre_id:
                self.sub_offre_id = False
        else:
            self.sub_offre_id = False
    
    @api.onchange('sub_offre_id')
    def _onchange_sub_offre_id(self):
        if self.sub_offre_id:
            self.offre_id = self.sub_offre_id.offre_id.id
            self.business_unit_id = self.sub_offre_id.offre_id.business_unit_id.id
    
    # ===== STATUT =====
    status = fields.Selection([
        ('new', 'Nouveau'),
        ('read', 'Lu'),
        ('qualified', 'Qualifié'),
        ('ignored', 'Ignoré'),
        ('converted', 'Converti en Lead')
    ], string='Statut', default='new')
    
    # ===== DATES =====
    publication_date = fields.Date(string='Date de publication')
    scraped_date = fields.Datetime(
        string='Date de détection',
        default=fields.Datetime.now
    )
    
    # ===== NOTES =====
    notes = fields.Text(string='Notes commerciales')
    
    # ===== LIEN VERS LEAD CRM =====
    lead_id = fields.Many2one('crm.lead', string='Lead CRM')
    
    # ===== MÉTHODE : CONVERTIR EN LEAD CRM =====

    
    def action_convert_to_lead(self):
        """Convertit l'offre en lead CRM avec création automatique du partner"""
        self.ensure_one()
        
        # Créer ou trouver le partner à partir de partner_name
        partner_id = False
        if self.partner_name:
            Partner = self.env['res.partner']
            existing_partner = Partner.search([
                ('name', '=ilike', self.partner_name.strip()),
                ('is_company', '=', True)
            ], limit=1)
            
            if existing_partner:
                partner_id = existing_partner.id
            else:
                new_partner = Partner.create({
                    'name': self.partner_name.strip(),
                    'is_company': True,
                    'email': self.email_from,
                    'phone': self.phone,
                })
                partner_id = new_partner.id
        
        # Créer le lead CRM
        lead_vals = {
            'name': self.name,
            'partner_name': self.partner_name,  # ✅ Champ Char, pas Many2one
            'email_from': self.email_from,
            'phone': self.phone,
            'description': self.description,
            'website': self.website,
            'Mode_de_livraison': self.Mode_de_livraison,
            'business_unit_id': self.business_unit_id.id,
            'offre_id': self.offre_id.id,
            'sub_offre_id': self.sub_offre_id.id,
            'source_id': self.source_id.id if self.source_id else False,
            'type': 'lead',
        }
        
        lead = self.env['crm.lead'].create(lead_vals)
        
        # Mettre à jour le statut
        self.write({
            'status': 'converted',
            'lead_id': lead.id
        })
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'crm.lead',
            'res_id': lead.id,
            'view_mode': 'form',
            'target': 'current',
        }