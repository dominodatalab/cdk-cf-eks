# Domino CDK to Terraform migration

Domino is deprecating this CDK repository, and switching all future EKS
provisioning work to our Terraform module, located here:

https://github.com/dominodatalab/terraform-aws-eks

The scripts in this directory will help you convert the management your
CDK-provisioned Domino infrastructure to the above Terraform module.

Your EKS cluster, EFS store, and S3 buckets will all remain in-tact.
The original ASGs and any bastion used for the install will be replaced
by ones generated in Terraform.

## Contents

* convert.py - The core migration script
* README.md - This file
* terraform/ - Terraform to take over CDK infrastructure
* cloudformation-only/ - Terraform to create a special IAM role to remove the CDK CloudFormation stack

## Migration steps

To convert the CDK stack to terraform, we will...

1. Create input variables into Terraform
2. Generate a set of Terraform import commands to import various AWS resources into the new Terraform
3. Initialize the Terraform directory and import the resources
4. Evaluate the Terraform plan
5. Apply the Terraform plan
6. Scale down the old auto-scaling groups
7. Validate Domino functionality
8. Delete unneeded AWS resources
9. Delete the old CloudFormation stack

### convert.py usage

    usage: convert.py [-h] {create-tfvars,resource-map,get-imports,delete-stack,print-stack} ...
    
    terraform eks module importer
    
    options:
      -h, --help            show this help message and exit
    
    commands:
      {create-tfvars,resource-map,get-imports,delete-stack,print-stack}
	create-tfvars       Generate tfvars
	resource-map        Create resource map for customization/debugging of get-imports command (optional step)
	get-imports         Get terraform import commands
	delete-stack        Get commands to delete old stack
	print-stack         Print CDK stack resources

### Create terraform variables

First, we must create the variables going into our Terraform config.

The following command will look at the current CDK stack and autopropagate the Terraform variables:

    ./convert.py create-tfvars --region us-east-1 --stack-name mystack --ssh-key-path /path/to/key.pem > terraform/terraform.tfvars.json

Note that the ssh key is handled different in the terraform module. With CDK,
we used an existing keypair, while the terraform module creates a keypair for
you. The local key does not need to be the one you used with CDK. The new
autoscaling group nodes and bastion node will be provisioned with the new key.

### Get AWS resources to import

Then, we'll use `convert.py` to generate the Terraform import commands to import our AWS resources:

    ./convert.py get-imports --region us-east-1 --stack-name mystack > terraform/imports.sh

### Initialize and import Terraform resources

Change to the `terraform/` directory, and run the following two commands:

    terraform init
    bash imports.sh

`imports.sh` will run *several* `terraform import` commands in a row. This is normal.

### Evaluate the Terraform plan

Once everything has been imported, you can run `terraform plan` and evaluate what terraform will do:

    terraform plan -out terraform.plan

There will be a lot of output, but near the end you should see output similar to this:

    Plan: 111 to add, 34 to change, 0 to destroy.

If there is anything Terraform plans to destroy, that is *not* expected and you should carefully scrutinize the output to ensure Terraform isn't doing anything destructive.

Regardless, you should peruse the output to understand what is going to happen. It should be creating new node groups, various security groups and IAM policies, a new bastion, and otherwise leaving things unchanged save for minor tag changes, etc. Major red flags would be large changes or delete/create cycles of the EKS cluster itself, S3 buckets, or EFS.

### Apply the terraform plan

If you're satisfied that the `terraform plan` output is reasonable, you can run `terraform apply`:

    terraform apply terraform.plan

Once Terraform is finished, the most critical work is done.

### Scale down the old autoscaling groups

You will have two sets of autoscaling groups at this point, so you will want to scale down the old ones.

Set min/max/desired to 0 on all CDK-provisioned auto-scaling groups.

The *old* ones look like this:

    clustername-platform-0-us-east-1

The *new* ones look like this:

    eks-clustername-platform-0-abcd1234-abcd-1234-5678-abcd12345678

Once all the Domino pods are live on the *new* nodes, Domino should be back up and functional.

### Delete unneeded AWS resources

There are various resources CDK managed, but terraform does not need, such as:

* The *old* autoscaling groups
* The *old* bastion and bastion EIP
* Various CDK lambdas and associated state machines
* Any network interfaces associated
* The `clustername-sharedNodeSG` security group
* The `clustername-endpoints` security group

There is a `clean-stack` command to help clean these up.

    ./convert.py clean-stack --region us-east-1 --stack-name mystack

You'll note that there is a comment about security groups:

    {'Security groups to be deleted': ['sg-06d2154938a2e4a07',
                                       'sg-03d806e3b0d455776']}

    However, some security groups have rules referencing them that must be removed:

    {'sg-06d2154938a2e4a07 is referenced by': {'sg-04396807b014ed3d5',
                                               'sg-0461c2c89e69acd81',
                                               'sg-06d2154938a2e4a07'}}

These rules aren't cleaned up automatically by default, as they can involve editing security groups outside the scope of the CloudFormation. You can choose to clean them up manually, or run with the `--remove-security-group-references` argument.

By default, this command does *not* actually make changes. To run the clean process for real, add `--delete`:

    ./convert.py clean-stack --region us-east-1 --stack-name mystack --delete [--remove-security-group-references]

### Delete the old cloudformation stack

Enter the `cloudformation-only/` subdirectory, and provision that terraform:

    cat <<EOF >> terraform.tfvars
    region="us-east-1"
    tags={}
    EOF
    terraform init
    terraform plan -out=terraform.plan
    terraform apply terraform.plan

This will provision an IAM role that *only has permission to CloudFormation and _nothing else_*.

Once this is provisioned, run `convert.py`'s `delete-stack` command and read its instructions:

    ./convert.py delete-stack --region us-east-1 --stack-name mystack
    
    Manual instructions:
    First run this delete-stack command using the cloudformation-only role:
    
    aws cloudformation delete-stack --region us-east-1 --stack-name mystack --role arn:aws:iam::1234567890:role/cloudformation-only
    
    This will *attempt* to delete the entire CDK stack, but *intentionally fail* so as to leave the stack in the delete failed state, with all resources having failed. This opens the gate to retain every resource, so the following runs can delete the stack(s) and only the stack(s). After running the first command, rerun this and then execute the following to safely delete the stacks:
    
    <various delete-stack commands for each stack, with the --retain-resources argument propagated>
    
    To perform this process automatically, add the --delete argument

Rerun the `delete-stack` command with `--delete` (or run the boto commands manually, if you prefer):

    ./convert.py delete-stack --region us-east-1 --stack-name mystack --delete

This may seem a bit strange, but there is no direct way to only remove a CloudFormation stack, while retaining all the resources. However, once a CloudFormation stack deletion even has failed, it is possible to re-attempt this stack deletion and specify failed resources to retain. So what this process does is use the limited permission role to cause all resource deletions to fail, and then specifies all extant resources as resources to retain on the subsequent attempt.

The reason the `convert.py delete-stack` must be rerun is the resources to retain need to be re-evaluated after the intial attempt, as a few CloudFormation-level resources *will* get successfully deleted (and that is normal).
