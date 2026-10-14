"""Crea la máquina gratuita de Oracle Cloud (Ampere A1) reintentando hasta que haya capacidad.

Oracle responde «Out of capacity» cuando no quedan máquinas ARM gratuitas en la región.
Este script lo reintenta cada pocos minutos y, cuando lo consigue, abre los puertos 80/443
y muestra la IP pública.

Requisitos:
    pip install oci
    ~/.oci/config con una clave API (Perfil → Tokens and keys → API keys → Add API key)

Uso:
    python deploy/oracle_retry.py --ssh-key ~/.ssh/bioyologic_oracle.pub
"""

from __future__ import annotations

import argparse
import base64
import random
import time
from datetime import datetime
from pathlib import Path

import oci
from oci.core import models as m

NAME = "bioyologic"
SHAPE = "VM.Standard.A1.Flex"
# Configuración automática al primer arranque (cloud-init): Docker, firewall, swap y el código.
CLOUD_INIT = """#cloud-config
package_update: true
packages: [docker.io, docker-compose-v2, git, git-lfs]
runcmd:
  - usermod -aG docker ubuntu
  - iptables -I INPUT 6 -p tcp -m multiport --dports 80,443 -j ACCEPT
  - netfilter-persistent save
  - fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  - echo '/swapfile none swap sw 0 0' >> /etc/fstab
  - sudo -u ubuntu git clone https://github.com/Godjuanjo/bioyologic.git /home/ubuntu/bioyologic
  - cd /home/ubuntu/bioyologic && sudo -u ubuntu git lfs pull
  - touch /home/ubuntu/.bioyologic-ready
"""

# Primero el tamaño completo gratuito; si no hay hueco, uno más pequeño (más fácil de conseguir).
# Tamaños más pequeños caben más fácil en los huecos que libera Oracle (Bioyologic usa ~1,2 GB).
SIZES = [(2, 12), (1, 6), (1, 4)]


def log(msg: str) -> None:
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def ensure_network(net, tenancy: str):
    """Devuelve una subred pública; crea VCN, gateway de internet y subred si no existen."""
    vcns = [v for v in net.list_vcns(tenancy).data if v.lifecycle_state == "AVAILABLE"]
    if vcns:
        vcn = vcns[0]
    else:
        log("Creando red virtual (VCN)…")
        vcn = net.create_vcn(m.CreateVcnDetails(compartment_id=tenancy, cidr_blocks=["10.0.0.0/16"],
                                                display_name=f"{NAME}-vcn", dns_label=NAME)).data
        vcn = oci.wait_until(net, net.get_vcn(vcn.id), "lifecycle_state", "AVAILABLE").data

    igws = net.list_internet_gateways(tenancy, vcn_id=vcn.id).data
    igw = igws[0] if igws else net.create_internet_gateway(m.CreateInternetGatewayDetails(
        compartment_id=tenancy, vcn_id=vcn.id, is_enabled=True, display_name=f"{NAME}-igw")).data
    rt = net.get_route_table(vcn.default_route_table_id).data
    if not any(r.destination == "0.0.0.0/0" for r in rt.route_rules):
        net.update_route_table(rt.id, m.UpdateRouteTableDetails(route_rules=rt.route_rules + [
            m.RouteRule(destination="0.0.0.0/0", destination_type="CIDR_BLOCK", network_entity_id=igw.id)]))

    subnets = [s for s in net.list_subnets(tenancy, vcn_id=vcn.id).data
               if not s.prohibit_public_ip_on_vnic and s.lifecycle_state == "AVAILABLE"]
    if subnets:
        return vcn, subnets[0]
    log("Creando subred pública…")
    sn = net.create_subnet(m.CreateSubnetDetails(
        compartment_id=tenancy, vcn_id=vcn.id, cidr_block="10.0.0.0/24", display_name=f"{NAME}-public",
        dns_label="public", route_table_id=vcn.default_route_table_id,
        security_list_ids=[vcn.default_security_list_id], prohibit_public_ip_on_vnic=False)).data
    return vcn, oci.wait_until(net, net.get_subnet(sn.id), "lifecycle_state", "AVAILABLE").data


def open_web_ports(net, subnet) -> None:
    """Abre HTTP (80) y HTTPS (443) en las listas de seguridad de la subred."""
    for sl_id in subnet.security_list_ids:
        sl = net.get_security_list(sl_id).data
        rules = list(sl.ingress_security_rules)
        open_ports = {r.tcp_options.destination_port_range.min for r in rules
                      if r.tcp_options and r.tcp_options.destination_port_range}
        new = [m.IngressSecurityRule(protocol="6", source="0.0.0.0/0", description=f"Bioyologic {p}",
                                     tcp_options=m.TcpOptions(destination_port_range=m.PortRange(min=p, max=p)))
               for p in (80, 443) if p not in open_ports]
        if new:
            net.update_security_list(sl_id, m.UpdateSecurityListDetails(ingress_security_rules=rules + new))
            log(f"Puertos abiertos en {sl.display_name}: {[r.tcp_options.destination_port_range.min for r in new]}")


def public_ip(compute, net, tenancy: str, instance_id: str) -> str | None:
    for att in compute.list_vnic_attachments(tenancy, instance_id=instance_id).data:
        vnic = net.get_vnic(att.vnic_id).data
        if vnic.public_ip:
            return vnic.public_ip
    return None


def patiently(fn, *args, tries: int = 20):
    """Reintenta si Oracle responde 401: una clave API recién creada tarda unos minutos en propagarse."""
    for i in range(tries):
        try:
            return fn(*args)
        except oci.exceptions.ServiceError as e:
            if e.status != 401 or i == tries - 1:
                raise
            log("La clave API aún se está activando en Oracle (401); espero 30 s…")
            time.sleep(30)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ssh-key", default=str(Path.home() / ".ssh" / "bioyologic_oracle.pub"))
    ap.add_argument("--every", type=int, default=60, help="segundos entre intentos")
    ap.add_argument("--profile", default="DEFAULT", help="perfil de ~/.oci/config (una cuenta de Oracle por perfil)")
    args = ap.parse_args()

    config = oci.config.from_file(profile_name=args.profile)
    log(f"Cuenta: perfil {args.profile}, región {config['region']}")
    oci.config.validate_config(config)
    tenancy = config["tenancy"]
    compute = oci.core.ComputeClient(config)
    net = oci.core.VirtualNetworkClient(config)
    identity = oci.identity.IdentityClient(config)

    existing = [i for i in patiently(lambda: compute.list_instances(tenancy, display_name=NAME)).data
                if i.lifecycle_state not in ("TERMINATED", "TERMINATING")]
    if existing:
        inst = existing[0]
        log(f"La instancia ya existe ({inst.lifecycle_state}).")
    else:
        ads = [a.name for a in patiently(identity.list_availability_domains, tenancy).data]
        # Cada intento prueba un dominio de fallo distinto (o ninguno): a veces uno concreto tiene hueco.
        fds = {ad: [None] + [f.name for f in patiently(lambda: identity.list_fault_domains(tenancy, ad)).data]
               for ad in ads}
        vcn, subnet = patiently(ensure_network, net, tenancy)
        patiently(open_web_ports, net, subnet)
        image = patiently(lambda: compute.list_images(
            tenancy, operating_system="Canonical Ubuntu", operating_system_version="24.04",
            shape=SHAPE, sort_by="TIMECREATED", sort_order="DESC").data[0])
        log(f"Imagen: {image.display_name}")
        ssh_key = Path(args.ssh_key).expanduser().read_text().strip()

        def find_existing():
            return [i for i in compute.list_instances(tenancy, display_name=NAME).data
                    if i.lifecycle_state not in ("TERMINATED", "TERMINATING")]

        attempt, inst = 0, None
        while inst is None:
            attempt += 1
            try:
                # Por si un intento anterior la creó pero se perdió la respuesta.
                found = find_existing()
            except (oci.exceptions.RequestException, oci.exceptions.ConnectTimeout, oci.exceptions.ServiceError) as e:
                log(f"Sin conexión con Oracle ({type(e).__name__}); reintento en 1 min")
                time.sleep(60)
                continue
            if found:
                inst = found[0]
                log(f"La instancia ya existe ({inst.lifecycle_state}).")
                break
            for ad in ads:
                fd = fds[ad][attempt % len(fds[ad])]
                where = fd.split("-")[-2] + "-" + fd.split("-")[-1] if fd else "cualquier dominio"
                for ocpus, mem in SIZES:
                    try:
                        inst = compute.launch_instance(m.LaunchInstanceDetails(
                            availability_domain=ad, fault_domain=fd, compartment_id=tenancy, display_name=NAME, shape=SHAPE,
                            shape_config=m.LaunchInstanceShapeConfigDetails(ocpus=ocpus, memory_in_gbs=mem),
                            source_details=m.InstanceSourceViaImageDetails(image_id=image.id,
                                                                           boot_volume_size_in_gbs=50),
                            create_vnic_details=m.CreateVnicDetails(subnet_id=subnet.id, assign_public_ip=True),
                            metadata={"ssh_authorized_keys": ssh_key,
                                      "user_data": base64.b64encode(CLOUD_INIT.encode()).decode()})).data
                        log(f"¡Conseguida! {ocpus} OCPU, {mem} GB en {ad} ({where})")
                        break
                    except (oci.exceptions.RequestException, oci.exceptions.ConnectTimeout) as e:
                        log(f"Intento {attempt}: fallo de red ({type(e).__name__}); se reintenta")
                    except oci.exceptions.ServiceError as e:
                        if e.status in (500, 503) or "capacity" in str(e.message).lower():
                            log(f"Intento {attempt}: sin capacidad ({ocpus} OCPU / {mem} GB, {where})")
                        elif e.status == 401:
                            log("Clave API aún activándose (401)")
                        elif e.status == 429:
                            log("Demasiadas peticiones; espero más")
                            time.sleep(60)
                        else:
                            raise
                if inst:
                    break
            if inst is None:
                time.sleep(args.every + random.randint(0, 15))

    inst = oci.wait_until(compute, compute.get_instance(inst.id), "lifecycle_state", "RUNNING",
                          max_wait_seconds=900).data
    ip = public_ip(compute, net, tenancy, inst.id)
    log(f"Instancia en marcha. IP pública: {ip}")
    log(f"Conéctate con: ssh -i ~/.ssh/bioyologic_oracle ubuntu@{ip}")
    (Path(__file__).with_name(".oracle_ip")).write_text(f"{ip} {args.profile} {config['region']}\n")


if __name__ == "__main__":
    main()
