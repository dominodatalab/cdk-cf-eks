resource "aws_vpc" "cdk_vpc" {
    tags = {
        Name = var.deploy_id
    }
}

resource "aws_eip" "nat_gateway" {
    count = var.number_of_azs

    tags = {
        Name                     = "${var.deploy_id}-public-${count.index+1}"
        "kubernetes.io/role/elb" = "1"
    }
}

resource "aws_nat_gateway" "public" {
    count = var.number_of_azs

    subnet_id     = aws_subnet.public[count.index].id
    allocation_id = aws_eip.nat_gateway[count.index].id

    tags = {
        Name                     = "${var.deploy_id}-public-${count.index+1}"
        "kubernetes.io/role/elb" = "1"
    }
}

resource "aws_internet_gateway" "cdk_vpc" {
    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name = var.deploy_id
    }
}

resource "aws_internet_gateway_attachment" "cdk_vpc" {
    internet_gateway_id = aws_internet_gateway.cdk_vpc.id
    vpc_id              = aws_vpc.cdk_vpc.id
}

resource "aws_subnet" "public" {
    count = var.number_of_azs

    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name                     = "${var.deploy_id}-public-${count.index+1}"
        "kubernetes.io/role/elb" = "1"
    }

    lifecycle {
        ignore_changes = [cidr_block]
    }
}

resource "aws_route_table" "public" {
    count = var.number_of_azs

    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name                     = "${var.deploy_id}-public-${count.index+1}"
        "kubernetes.io/role/elb" = "1"
    }
}

resource "aws_route_table_association" "public" {
    count = var.number_of_azs

    subnet_id      = aws_subnet.public[count.index].id
    route_table_id = aws_route_table.public[count.index].id
}

resource "aws_subnet" "private" {
    count = var.number_of_azs

    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name                              = "${var.deploy_id}-private-${count.index+1}"
        "kubernetes.io/role/internal-elb" = "1"
    }

    lifecycle {
        ignore_changes = [cidr_block]
    }
}

resource "aws_route_table" "private" {
    count = var.number_of_azs

    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name                              = "${var.deploy_id}-private-${count.index+1}"
        "kubernetes.io/role/internal-elb" = "1"
    }
}

resource "aws_route_table_association" "private" {
    count = var.number_of_azs

    subnet_id      = aws_subnet.private[count.index].id
    route_table_id = aws_route_table.private[count.index].id
}

resource "aws_subnet" "pod" {
    count = var.number_of_azs

    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name                              = "${var.deploy_id}-pod-${count.index+1}"
    }

    lifecycle {
        ignore_changes = [cidr_block]
    }
}

resource "aws_route_table" "pod" {
    count = var.number_of_azs

    vpc_id = aws_vpc.cdk_vpc.id

    tags = {
        Name                              = "${var.deploy_id}-pod-${count.index+1}"
    }
}

resource "aws_route_table_association" "pod" {
    count = var.number_of_azs

    subnet_id      = aws_subnet.pod[count.index].id
    route_table_id = aws_route_table.pod[count.index].id
}