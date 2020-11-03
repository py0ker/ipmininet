import ipaddress
import itertools
import random

from ipmininet.iptopo import IPTopo
from ipmininet.router.config import ebgp_session, RouterConfig, BGP, ExaBGPDaemon, BGPRoute, BGPAttribute, \
    ExaList
import ipmininet.router.config.bgp as _bgp

__MAX_UINT32_ = 4294967295


def list_of_rnd_lists(nb, max_sub_rnd_list):
    def random_gen(low, high):
        while True:
            yield random.randrange(low, high)

    rnd_lists = []

    for _ in range(0, nb):
        rnd_set = set()
        gen = random_gen(1, 65536)
        rnd_path_len = random.randint(1, max_sub_rnd_list)

        # Try to add elem to set until set length is less than 'rnd_path_len'
        for x in itertools.takewhile(lambda y: len(rnd_set) <= rnd_path_len, gen):
            rnd_set.add(x)

        rnd_lists.append(list(rnd_set))

    return rnd_lists


def rnd_list(max_sub_rnd_list, strict=False):
    def random_gen(low, high):
        while True:
            yield random.randrange(low, high)

    rnd_set = set()
    gen = random_gen(1, 65536)
    rnd_path_len = random.randint(1, max_sub_rnd_list) if not strict else max_sub_rnd_list

    for x in itertools.takewhile(lambda y: len(rnd_set) <= rnd_path_len, gen):
        rnd_set.add(x)

    return list(rnd_set)


def build_bgp_route(ip_networks, my_as):

    my_routes = list()

    for ip_network in ip_networks:
        next_hop = BGPAttribute("next-hop", "self")
        as_path = BGPAttribute("as-path", ExaList([my_as] + rnd_list(random.randint(1, 25))))
        communities = BGPAttribute("community",
                                   ExaList(["%d:%d" % (j, k) for j, k in zip(rnd_list(24, True), rnd_list(24, True))]))
        med = BGPAttribute("med", random.randint(1, __MAX_UINT32_))
        origin = BGPAttribute("origin", random.choice(["igp", "egp", "incomplete"]))

        my_routes.append(BGPRoute(ip_network, [next_hop, origin, med, as_path, communities]))

    return my_routes


class ExaBGPTopoInjectPrefixes(IPTopo):
    """
    This simple topology made up of 2 routers, as1 and as2 from both different
    ASN, shows an example on how to use ExaBGP to inject both IPv4 and IPv6
    routes to its remote peer.
    """

    @staticmethod
    def gen_simple_prefixes_v4(my_as):
        pfxs = (ipaddress.ip_network("8.8.8.0/24"),
                ipaddress.ip_network("19.145.206.163/32"),
                ipaddress.ip_network("140.182.0.0/16"),)

        return build_bgp_route(pfxs, my_as)

    @staticmethod
    def gen_simple_prefixes_v6(my_as):
        pfxs = (ipaddress.ip_network("c0ff:ee:beef::/56"),
                ipaddress.ip_network("1:ea7:dead:beef::/64"),
                ipaddress.ip_network("d0d0:15:dead::/48"))

        return build_bgp_route(pfxs, my_as)

    def build(self, *args, **kwargs):
        """
         +--+--+     +--+--+
         | as1 +-----+ as2 |
         +--+--+     +--+--+
        """

        af4 = _bgp.AF_INET(routes=self.gen_simple_prefixes_v4(1))
        af6 = _bgp.AF_INET6(routes=self.gen_simple_prefixes_v6(1))

        # Add all routers
        as1r1 = self.addRouter("as1", config=RouterConfig, use_v4=True, use_v6=True)
        as1r1.addDaemon(ExaBGPDaemon, address_families=(af4, af6))

        as2r1 = self.bgp('as2')

        # Add links
        las12 = self.addLink(as1r1, as2r1)
        las12[as1r1].addParams(ip=("fd00:12::1/64",))
        las12[as2r1].addParams(ip=("fd00:12::2/64",))

        # Set AS-ownerships
        self.addAS(1, (as1r1,))
        self.addAS(2, (as2r1,))
        # Add eBGP peering
        ebgp_session(self, as1r1, as2r1)

        # Add test hosts
        for r in self.routers():
            self.addLink(r, self.addHost('h%s' % r))
        super().build(*args, **kwargs)

    def bgp(self, name):
        r = self.addRouter(name, use_v4=True, use_v6=True)
        r.addDaemon(BGP, address_families=(
            _bgp.AF_INET(redistribute=('connected',)),
            _bgp.AF_INET6(redistribute=('connected',))))
        return r